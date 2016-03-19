#!/usr/bin/env python
# -*- coding:utf-8 -*-
import traceback
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

        self.parse_summary()
        self.parse_chapters()

    def soup_for(self, url):
        try:
            html = requests.get(url).text
        except Exception as exc:
            raise Exception('Could not access post at %s. Cause : %s', url, exc)
        return BeautifulSoup(html, "lxml")

    def parse_chapters(self):
        #  for name, url in self.all_chapters_url:
        #    self.parse_chapter(url)
        self.first_chapter = self.parse_chapter(self.all_chapters_url[0][1])
        self.chapters_content.append((self.all_chapters_url[0][0], self.first_chapter))

    def parse_summary(self):
        logger.info('Parsing summary at %s', self.base_url)
        soup = self.soup_for(self.base_url)
        self.introduction = soup.article
        try:
            self.title = soup.find('h1').text
            self.author = soup.find('h3').find('a').text
        except:
            logger.warning('Could not read the author or the title')

        all_chapters_link = self.introduction.find_all('a')
        for tag_a in all_chapters_link:
            self.all_chapters_url.append((tag_a.text, tag_a.get('href')))
            tag_a.extract()
        self.get_images(self.introduction)
        self.introduction = self.introduction.prettify()
        logger.info('Summary parsed !')

    def parse_chapter(self, url):
        """
        Given an internal link to a post on Paradox forums, read the HTML page
        where the post lives, and extract the given post information.
        """
        soup = self.soup_for(url)
        id_post = url[url.rfind('#') + 1:].replace('post', 'post-')
        logger.info('Looking for post #%s at %s', id_post, url)
        post = soup.find(id=id_post)
        self.get_images(post.article)
        return post.article.prettify()

    def get_images(self, article_soup):
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
        # Cache images to avoid downloading the same one multiple times
        if url in self.images.keys():
            return self.images[url]
        logger.info('Trying to download image at %s', url)
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
    author = parser.author
    title = parser.title
    chapters = [('Introduction', parser.introduction),
                parser.chapters_content[0]]

    book = epub.EpubBook()
    book.set_title(title)
    book.set_language('en')
    book.add_author(author)
    chapters_info = []
    chapters_obj = []
    for idx, (sub_title, html_parsed) in enumerate(chapters):
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
