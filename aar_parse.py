#!/usr/bin/env python
# -*- coding:utf-8 -*-
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


class AARParser(object):
    def __init__(self, temp_dir, base_url):
        if not urlparse(base_url).hostname == PARADOX_FORUM:
            raise ValueError('Not a paradox forum URL.')
        self.temp_dir = temp_dir
        self.title = 'Unknown'
        self.author = 'Unknown'
        self.base_url = base_url
        self.all_chapters_url = []
        self.chapters_content = []
        self.images = {}

        self.parse_summary_and_toc()
        self.parse_chapters()

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
        chapter_count = 1
        for tag_a in all_chapters_link:
            # Sometimes, there will be a link to another thread or something
            # entirely different in the TOC. Let's only take link in the same
            # thread.
            href = tag_a.get('href')
            if href.find(thread_id) >= 0:
                try:
                    urlparse(href)
                    self.all_chapters_url.append((tag_a.text, href))
                    # Replace the link so it becomes a local, epub one
                    # (only works if introduction and TOC are in the same place)
                    tag_a['href'] = 'chapter_%d.xhtml' % chapter_count
                    chapter_count += 1
                except ValueError:
                    logger.warning('Rejected invalid URL : %s' % href)
            else:
                logger.warning('Rejecting link %s not linked to thread id %s',
                               href, thread_id)
        self.get_images(introduction)
        self.chapters_content.append(('Introduction', introduction.prettify()))
        logger.info('Summary parsed.')

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
        for name, url in self.all_chapters_url:
            content = self.parse_chapter(url)
            if content:
                self.chapters_content.append((name, content))

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
            self.get_images(post.article)
            logger.info('Done.')
            return post.article.prettify()
        else:
            logger.warning('Cannot find article for post %s' % id_post)

    def get_images(self, article_soup):
        """
        Try to get every images contained in an "article" tag.
        Change the src path for those images so they're properly displayed
        in the epub (and not loaded from the Internet, where things, and
        particularly images, tend to disappear suddenly).
        """
        to_delete = []
        for img in article_soup.find_all('img'):
            img_src = img.get('src')
            # If there is no hostname, it's probably a smiley or any image
            # directly hosted on the forum; we don't want those.
            hostname = urlparse(img_src).hostname
            if img_src and hostname:
                image_name = self.download_image(img_src)
                if not image_name:
                    to_delete.append(img)
                else:
                    img['src'] = os.path.join('images/%s' % image_name)
            else:
                to_delete.append(img)
        for void_imgs in img:
            void_imgs.extract()

    def download_image(self, url):
        """
        Download an image from its url, store it in a temporary folder.
        """
        # Cache images to avoid downloading the same one multiple times
        if url in self.images.keys():
            return self.images[url]
        logger.info('Downloading image at %s', url)
        r = requests.get(url, stream=True)
        if r.status_code == 200:
            img_name = url[url.rfind('/') + 1:]
            img_path = os.path.join(self.temp_dir, img_name)
            with open(img_path, 'w') as f:
                r.raw.decode_content = True
                shutil.copyfileobj(r.raw, f)
            self.images[url] = img_path
            return img_name
        return None


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
    for idx, (sub_title, html_parsed) in enumerate(parser.chapters_content):
        file_name = 'chapter_%d.xhtml' % idx
        c = epub.EpubHtml(title=sub_title, file_name=file_name)
        c.content = html_parsed
        chapters_info.append((file_name, title, ''))
        book.add_item(c)
        chapters_obj.append(c)
    for image in parser.images.values():
        img = epub.EpubImage()
        img.file_name = 'images/%s' % image[image.rfind('/') + 1:]
        img.content = open(image, 'rb').read()
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
