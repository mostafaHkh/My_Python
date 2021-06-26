# -*- coding: utf-8 -*-

import logging
import requests
from bs4 import BeautifulSoup
import collections
import doi

logger = logging.getLogger('scihub')

HEADERS = {
    'User-Agent':
    'Mozilla/5.0 (compatible; MSIE 9.0; Windows NT 6.1; Trident/5.0)'
}

AVAILABLE_SCIHUB_BASE_URL = [
    "sci-hub.tw",
    "sci-hub.is",
    "sci-hub.sci-hub.tw",
    "80.82.77.84",
    "80.82.77.83",
    "sci-hub.mn",
    "sci-hub.la",
    "sci-hub.io",
    "sci-hub.hk",
    "sci-hub.bz",
    "tree.sci-hub.la",
    "sci-hub.ws",
    "sci-hub.tv",
    "sci-hub.sci-hub.tv",
    "sci-hub.sci-hub.mn",
    "sci-hub.sci-hub.hk",
    "sci-hub.name",
    "sci-hub.cc",
    "www.sci-hub.cn",
    "sci-hub.biz",
    "sci-hub.ac",
]


Context = collections.namedtuple('Context', ['pdf', 'url', 'doi'])


class SciHub(object):
    """
    SciHub class can fetch/download papers from sci-hub.io
    """

    def __init__(self, uri,
                 base_urls=AVAILABLE_SCIHUB_BASE_URL, headers=HEADERS):
        self.uri = uri
        self.session = requests.Session()
        self.session.headers = headers
        self.available_base_url_list = base_urls
        self.tries = 0
        self.current_base_url_index = 0
        self.doi = ''

    @property
    def base_url(self):
        return 'https://{0}/'.format(
            self.available_base_url_list[self.current_base_url_index]
        )

    def _change_base_url(self):
        self.current_base_url_index += 1

        if self.current_base_url_index >= len(self.available_base_url_list):
            raise Exception("No more scihub urls available, none are working")

        logger.info(
            "Changing to {0}".format(
                self.available_base_url_list[self.current_base_url_index]
            )
        )

    def fetch(self):
        """
        Fetches the paper by first retrieving the direct link to the pdf.
        If the indentifier is a DOI, PMID, or URL pay-wall, then use Sci-Hub
        to access and download paper. Otherwise, just download paper directly.
        """
        logger.info('Downloading with {1}'.format(self.tries, self.base_url))
        try:
            url = self._search_direct_url()
        except Exception as e:
            self._change_base_url()
            raise e
        else:
            if url is None:
                self._change_base_url()
                raise DocumentUrlNotFound('Direct url could not be retrieved')

        logger.info('direct_url = {0}'.format(url))

        try:
            # verify=False is dangerous but sci-hub.io
            # requires intermediate certificates to verify
            # and requests doesn't know how to download them.
            # as a hacky fix, you can add them to your store
            # and verifying would work. will fix this later.
            res = self.session.get(url, verify=False)

            if res.headers['Content-Type'] != 'application/pdf':
                self._change_base_url()
                logger.warning('CAPTCHA needed')
                raise CaptchaNeededException(
                    'Failed to fetch pdf with identifier {0}'
                    '(resolved url {1}) due to captcha'
                    .format(self.uri, url),
                    url
                )
            else:
                return Context(pdf=res.content, url=url, doi=self.doi)

        except requests.exceptions.ConnectionError:
            logger.error(
                '{0} cannot acess,changing'.format(
                    self.available_base_url_list[0]
                )
            )
            self._change_base_url()

        except requests.exceptions.RequestException as e:
            return dict(
                err='Failed to fetch pdf with identifier %s '
                    '(resolved url %s) due to request exception.' % (
                        self.uri, url
                    )
            )

    def _search_direct_url(self):
        """
        Sci-Hub embeds papers in an iframe. This function finds the actual
        source url which looks something like

            https://moscow.sci-hub.io/.../....pdf.
        """

        logger.debug('pinging {0}'.format(self.base_url))
        ping = self.session.get(self.base_url, timeout=1, verify=False)
        if not ping.status_code == 200:
            logger.error('server {0} is down '.format(self.base_url))
            return None

        logger.debug('server {0} is up'.format(self.base_url))
        url = "{0}{1}".format(self.base_url, self.uri)
        logger.debug('scihub url {0}'.format(url))
        res = self.session.get(url, verify=False)
        logger.debug('Scraping scihub site')
        logger.debug('trying to get doi')
        self.doi = doi.find_doi_in_text(res.content.decode('utf8')) or ''
        if self.doi:
            logger.info('found a doi candidate {0}'.format(self.doi))
        s = BeautifulSoup(res.content, 'html.parser')
        iframe = s.find('iframe')
        if iframe:
            logger.debug('iframe found in scihub\'s html')
            return (
                iframe.get('src')
                if not iframe.get('src').startswith('//')
                else 'https:' + iframe.get('src')
            )


class CaptchaNeededException(Exception):

    def __init__(self, msg, url):
        self.captcha_url = url
        Exception.__init__(self, msg)


class DocumentUrlNotFound(Exception):
    pass
