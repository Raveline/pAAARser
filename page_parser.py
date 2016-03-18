import logging
import sys

import requests
from bs4 import BeautifulSoup
from ebooklib import epub


logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)


def parse_chapter(url):
    html = requests.get(url).text
    id_post = url[url.rfind('#') + 1:].replace('post', 'post-')
    logger.info('Looking for post #%s' % id_post)
    soup = BeautifulSoup(html)
    post = soup.find(id=id_post)
    return post.article


def to_epub(author, title, chapters):
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
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    book.spine = ['nav']
    book.spine += chapters_obj
    epub.write_epub(title.replace(' ', '_') + '.epub', book, {})


def read_summary(url):
    html = requests.get(url).text
    soup = BeautifulSoup(html)
    introduction = soup.article
    try:
        aar_title = soup.find('h1').text
        aar_author = soup.find('h3').find('a').text
    except:
        logger.error('Could not read the author or the title')
        aar_author, aar_title = 'Unknown'

    all_chapters = introduction.find_all('a')
    all_chapters = [(chapter.get('href'), chapter.text)
                    for chapter in all_chapters]
    first_chapter = parse_chapter(all_chapters[0][0])

    to_epub(aar_author, aar_title, [('Introduction', introduction.prettify()),
                                    (all_chapters[0][1], first_chapter.prettify())])


if __name__ == "__main__":
    read_summary(sys.argv[1])
