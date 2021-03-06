from __future__ import absolute_import, print_function

import json
import os
import logging
import gzip
import solr
from elasticsearch import Elasticsearch, helpers


from topik.utils import batch_concat

logging.basicConfig(format='%(asctime)s : %(levelname)s : %(message)s', level=logging.INFO)


def iter_document_json_stream(filename, field):
    """Iterate over a json stream of items and get the field that contains the text to process and tokenize.

    Parameters
    ----------
    filename: string
        The filename of the json stream.

    field: string
        The field name that contains the text that needs to be processed

    $ head -n 2 ./topik/tests/data/test-data-1
        {"id": 1, "topic": "interstellar film review", "text":"'Interstellar' was incredible. The visuals, the score..."}
        {"id": 2, "topic": "big data", "text": "Big Data are becoming a new technology focus both in science and in..."}
    >>> document = iter_document_json_stream('./topik/tests/test-data-1.json', "text")
    >>> next(document)[1]
    [u"'Interstellar' was incredible. The visuals, the score, the acting, were all amazing. The plot is definitely one
    of the most original I've seen in a while."]

    """
    with open(filename, 'r') as f:
        for n, line in enumerate(f):
            try:
                dictionary = json.loads(line)
                content = dictionary.get(field)
                id = "%s/%s[%d]" % (filename, field, n)
                yield id, content
            except ValueError:
                logging.warning("Unable to process line: %s" %
                                str(line))


def iter_documents_folder(folder):
    """Iterate over the files in a folder to retrieve the content to process and tokenize.

    Parameters
    ----------
    folder: string
        The folder containing the files you want to analyze.

    $ ls ./topik/tests/test-data-folder
        doc1  doc2  doc3
    >>> doc_text = iter_documents_folder('./topik/tests/test-data-1.json')
    >>> fullpath, content = next(doc_text)
    >>> content
    [u"'Interstellar' was incredible. The visuals, the score, the acting, were all amazing. The plot is definitely one
    of the most original I've seen in a while."]

    """
    for directory, subdirectories, files in os.walk(folder):
        for file in files:
            _open = gzip.open if file.endswith('.gz') else open
            try:
                fullpath = os.path.join(directory, file)
                with _open(fullpath, 'rb') as f:
                    yield fullpath, f.read().decode('utf-8')
            except (ValueError, UnicodeDecodeError) as err:
                logging.warning("Unable to process file: %s" % fullpath)


def iter_large_json(json_file, prefix_value, event_value):
    import ijson

    parser = ijson.parse(open(json_file))

    for prefix, event, value in parser:
        # For Flowdock data ('item.content', 'string')
        if (prefix, event) == (prefix_value, event_value):
            yield "%s/%s" % (prefix, event), value


def iter_solr_query(solr_instance, field, query="*:*"):
    s = solr.SolrConnection(solr_instance)
    response = s.query(query)
    return batch_concat(response, field,  content_in_list=False)


def iter_elastic_query(instance, index, field, subfield=None):
    es = Elasticsearch(instance)

    # initial search
    resp = es.search(index, body={"query": {"match_all": {}}}, scroll='5m')

    scroll_id = resp.get('_scroll_id')
    if scroll_id is None:
        return

    first_run = True
    while True:
        for hit in resp['hits']['hits']:
            s = hit['_source']
            try:
                if subfield is not None:
                    yield "%s/%s" % (field, subfield), s[field][subfield]
                else:
                    yield field, s[field]
            except ValueError:
                    logging.warning("Unable to process row: %s" %
                                    str(hit))

        scroll_id = resp.get('_scroll_id')
        # end of scroll
        if scroll_id is None or not resp['hits']['hits']:
            break
