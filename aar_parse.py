#!/usr/bin/env python
# -*- coding:utf-8 -*-
import multiprocessing
import traceback
import operator
import os
import logging
import sys
import tempfile
import shutil
from urlparse import urlparse

import requests
from bs4 import BeautifulSoup
from ebooklib import epub


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


PARADOX_FORUM = 'forum.paradoxplaza.com'


class Image(object):
    def __init__(self, url, path_dir):
        self.url = url
        self.name = url[url.rfind('/') + 1:]
        self.path = os.path.join(path_dir, self.name)
        self.downloaded = False


class AARParser(object):
    def __init__(self, temp_dir, base_url):
        if not urlparse(base_url).hostname == PARADOX_FORUM:
            raise ValueError('Not a paradox forum URL.')
        self.temp_dir = temp_dir
        self.title = 'Unknown'
        self.author = 'Unknown'
        self.base_url = base_url

        self.chapters_to_process = []
        self.processed_chapters = {}

        self.images_to_process = []
        self.known_images_url = set()
        self.processed_images = {}

        self.parse_summary_and_toc()
        self.parse_chapters()
        self.download_all_images()
        self.fix_links()

    def soup_for(self, url):
        try:
            html = requests.get(url).text
        except Exception as exc:
            raise Exception('Could not access post at %s. Cause : %s', url, exc)
        return BeautifulSoup(html, "lxml")

    def parse_summary_and_toc(self):
        logger.info('Parsing summary at %s', self.base_url)
        thread_id_start = self.base_url.rfind('.')
        thread_id_end = self.base_url.rfind('/')
        thread_id = self.base_url[thread_id_start + 1:thread_id_end]
        soup = self.soup_for(self.base_url)
        introduction = soup.article
        try:
            self.title = soup.find('h1').text
            self.author = soup.find('h3').find('a').text
        except:
            logger.warning('Could not read the author or the title')

        toc_post = self.identify_toc(soup)
        all_chapters_link = toc_post.find_all('a')
        for tag_a in all_chapters_link:
            # Sometimes, there will be a link to another thread or something
            # entirely different in the TOC. Let's only take link in the same
            # thread.
            href = tag_a.get('href')
            if href.find(thread_id) >= 0:
                try:
                    urlparse(href)
                    self.chapters_to_process.append((tag_a.text, href))
                except ValueError:
                    logger.warning('Rejected invalid URL : %s' % href)
            else:
                logger.warning('Rejecting link %s not linked to thread id %s',
                               href, thread_id)
        self.parse_images(introduction)
        self.add_chapter(self.base_url, 'Introduction', introduction, 0)
        logger.info('Summary parsed.')

    def add_chapter(self, url, name, soup, order):
        self.processed_chapters[url] = {
            'name': name, 'soup': soup, 'order': order
        }

    def identify_toc(self, first_page):
        """
        The TOC is not ALWAYS in the first post of the thread, so we need
        to be able to detect the post containing the TOC.
        We will use a basic heuristic : the TOC is the article on first
        page with the most links. NB: if the TOC is not on the first page, we
        are screwed.
        """
        all_first_page_articles = first_page.find_all('article')
        # Use a list rather than a dict ot have article in order
        # Chances are, the first article with the most link is the TOC
        articles_and_count = []
        for article in all_first_page_articles:
            all_links = article.find_all('a')
            articles_and_count.append((article, len(all_links)))
        return max(articles_and_count, key=operator.itemgetter(1))[0]

    def parse_chapters(self):
        for idx, (name, url) in enumerate(self.chapters_to_process):
            content = self.parse_chapter(url)
            if content:
                self.add_chapter(url, name, content, idx + 1)
            else:
                logger.warning('Could not find content in post at %s' % url)

    def parse_chapter(self, url):
        """
        Given an internal link to a post on Paradox forums, read the HTML page
        where the post lives, and extract the given post information.
        """
        soup = self.soup_for(url)
        id_post = url[url.rfind('#') + 1:]
        if id_post.find('post-') == -1:
            id_post = id_post.replace('post', 'post-')
        logger.info('Parsing post #%s at %s', id_post, url)
        post = soup.find(id=id_post)
        if post and hasattr(post, 'article'):
            logger.info('Done.')
            self.parse_images(post.article)
            return post.article
        else:
            logger.warning('Cannot find article for post %s' % id_post)

    def parse_images(self, article_soup):
        """
        Try to get every images contained in an "article" tag.
        Change the src path for those images so they're properly displayed
        in the epub (and not loaded from the Internet, where things, and
        particularly images, tend to disappear suddenly).
        """
        for img in article_soup.find_all('img'):
            img_src = img.get('src')
            if img_src not in self.known_images_url:
                # If there is no hostname, it's probably a smiley or any image
                # directly hosted on the forum; we don't want those.
                hostname = urlparse(img_src).hostname
                if img_src and hostname:
                    self.images_to_process.append(Image(img_src, self.temp_dir))
                    self.known_images_url.add(img_src)

    def download_all_images(self):
        """
        Multiprocess getting the image to avoid losing too much time
        on network wait
        """
        manager = multiprocessing.Manager()
        processes = []
        results = manager.list()
        for img in self.images_to_process:
            processes.append(multiprocessing.Process(
                target=self.download_image,
                args=(img, results))
            )
        for p in processes:
            p.start()
        for p in processes:
            p.join()
        self.processed_images = {img.url: img
                                 for img in results if img.downloaded}

    def fix_links(self):
        for element in self.processed_chapters.values():
            # Replace image links
            for img in element['soup'].find_all('img'):
                new_link = self.processed_images.get(img['src'])
                if new_link:
                    img['src'] = os.path.join('images/%s' % new_link.name)
                else:
                    logger.warning('Image %s could not be downloaded, will be'
                                   ' removed.', img['src'])
                    img.extract()
            for a in element['soup'].find_all('a'):
                internal_dest = self.processed_chapters.get(a.get('href'))
                if internal_dest:
                    a['href'] = 'chapter_%d.xhtml' % internal_dest['order']

    def download_image(self, image, results):
        """
        Download an image from its url, store it in a temporary folder.
        """
        logger.info('Downloading image at %s', image.url)
        r = requests.get(image.url, stream=True)
        if r.status_code == 200:
            with open(image.path, 'w') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
            image.downloaded = True
        results.append(image)

    def get_chapters_content(self):
        return sorted(self.processed_chapters.values(),
                      key=lambda ch: ch['order'])


def to_epub(parser):
    """
    God this function is ugly.
    """
    author = parser.author
    title = parser.title

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language('en')
    book.add_author(author)
    chapters_info = []
    chapters_obj = []
    for chapter in parser.get_chapters_content():
        file_name = 'chapter_%d.xhtml' % chapter['order']
        c = epub.EpubHtml(title=chapter['name'], file_name=file_name)
        c.content = chapter['soup'].prettify()
        chapters_info.append((file_name, title, ''))
        book.add_item(c)
        chapters_obj.append(c)
    for image in parser.processed_images.values():
        img = epub.EpubImage()
        img.file_name = 'images/%s' % image.name
        img.content = open(image.path, 'rb').read()
        book.add_item(img)
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav']
    book.spine += chapters_obj
    epub.write_epub(title.replace(' ', '_') + '.epub', book, {})


if __name__ == "__main__":
    if len(sys.argv) != 2:
        logger.error('Invalid call. Usage: aar_parse.py "<url of base post>"')
        exit(1)
    try:
        temp_dir = tempfile.mkdtemp()
        parser = AARParser(temp_dir, sys.argv[1])
        to_epub(parser)
    except ValueError as exc:
        logger.error(traceback.format_exc(exc))
        logger.error('Could not get the AAR. Cause : %s', exc)
    finally:
        shutil.rmtree(temp_dir)
