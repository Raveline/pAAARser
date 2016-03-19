# pAARser

This is a script to download an After Action Report (AAR) from Paradox Forum and turn it into an ebook.
NOTE: I don't know Paradox policy when it comes to parsing its forum, and they might object to it.
(I shall update this as soon as I know what is their view on this matter).

## Installation

pAARser uses mostly three python libraries:

- Requests
- BeautifulSoup4
- EbookLib.

BeautifulSoup4 need several packages. If you don't have those installed, you probably want to install
the development packages for libxml2, libxslt1, zlib1g, and of course, libpython-dev. (Please refer to
your distrubtion).

Once you've got those, a classic

    pip install -r requirements

Should do the trick (execute this as root if you're not in a virtual environment).

## Usage

Pick the URL of the thread and do:

    python aar_parse.py <url>

(Or simply make the script executable and call it directly)

Then wait (depending on the size of the AAR and the quantity of images). The epub will appear in the current
directory.

(NB : your mileage may vary, but you can of course report any bug on the issue page).

## Plans for feature-creep

- Add covers (with the author profile pic ?).
- Add stylesheet. (Ideally, a different CSS for different games).
- Add a real TOC.

## Licence, smallprints and videotapes

This tool is under the AGPL licence.

If you use this script to commit crimes, read inflammatory prose, destroy the world, become addicted to Paradox
products or spread this dangerous addiction, kill your social life, become a sentient fungus bent on controlling
the universe or more generally, anything harmful to you, your species, or really any other species,
please do not sue me.
