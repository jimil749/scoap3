import json
import logging
import os
import re

import pycountry
from django.core.exceptions import ValidationError
from django.core.files.storage import storages
from django.core.management.base import BaseCommand, CommandParser
from django.core.validators import URLValidator

from scoap3.articles.models import Article, ArticleIdentifier
from scoap3.authors.models import Author, AuthorIdentifier
from scoap3.misc.models import (
    Affiliation,
    ArticleArxivCategory,
    Copyright,
    Country,
    ExperimentalCollaboration,
    License,
    PublicationInfo,
    Publisher,
)

logger = logging.getLogger(__name__)

# TODO Remove at some point
MAX_AUTHORS = 10


def _rename_keys(data, replacements):
    for item in data:
        for old_key, new_key in replacements:
            if old_key in item:
                item[new_key] = item.pop(old_key)
    return data


def _create_licenses(data):
    licenses = []
    val = URLValidator()
    for license in _rename_keys(data, [("license", "name")]):
        try:
            val(license.get("url"))
        except ValidationError:
            if license.get("name") is None:
                license["name"] = license.get("url")
            license.pop("url")

        if (
            license["name"] == "CC-BY-4.0"
            or license["name"] == "Creative Commons Attribution 4.0 licence"
        ):
            license["name"] = "CC-BY-4.0"
            license["url"] = "http://creativecommons.org/licenses/by/4.0/"
        elif (
            license["name"] == "CC-BY-3.0"
            or license["name"] == "Creative Commons Attribution 3.0 licence"
        ):
            license["name"] = "CC-BY-3.0"
            license["url"] = "http://creativecommons.org/licenses/by/3.0/"

        license, _ = License.objects.get_or_create(
            url=license.get("url", ""), name=license.get("name", "")
        )
        licenses.append(license)
    return licenses


def _create_article(data, licenses):
    article_data = {
        "id": data.get("control_number"),
        "publication_date": data["imprints"][0].get("date"),
        "title": data["titles"][0].get("title"),
        "subtitle": data["titles"][0].get("subtitle", "")[:255],
        "abstract": data["abstracts"][0].get("value", ""),
    }
    article, _ = Article.objects.get_or_create(**article_data)
    article.related_licenses.set(licenses)
    return article


def _create_article_identifier(data, article):
    for doi in data.get("dois"):
        article_identifier_data = {
            "article_id": article,
            "identifier_type": "DOI",
            "identifier_value": doi.get("value"),
        }
        ArticleIdentifier.objects.get_or_create(**article_identifier_data)

    for arxiv in data.get("arxiv_eprints", []):
        article_identifier_data = {
            "article_id": article,
            "identifier_type": "arXiv",
            "identifier_value": arxiv.get("value"),
        }
        ArticleIdentifier.objects.get_or_create(**article_identifier_data)


def _create_copyright(data, article):
    for copyright in data.get("copyright", []):
        copyright_data = {
            "article_id": article,
            "statement": copyright.get("statement", ""),
            "holder": copyright.get("holder", ""),
            "year": copyright.get("year"),
        }
        Copyright.objects.get_or_create(**copyright_data)


def _create_article_arxiv_category(data, article):
    if "arxiv_eprints" in data.keys():
        for idx, arxiv_category in enumerate(
            data["arxiv_eprints"][0].get("categories", [])
        ):
            article_arxiv_category_data = {
                "article_id": article,
                "category": arxiv_category,
                "primary": True if idx == 0 else False,
            }

            ArticleArxivCategory.objects.get_or_create(**article_arxiv_category_data)


def _create_publisher(data):
    publishers = []
    for imprint in data.get("imprints"):
        publisher_data = {
            "name": imprint.get("publisher"),
        }
        publisher, _ = Publisher.objects.get_or_create(**publisher_data)
        publishers.append(publisher)
    return publishers


def _create_publication_info(data, article, publishers):
    for idx, publication_info in enumerate(data.get("publication_info", [])):
        publication_info_data = {
            "article_id": article,
            "journal_volume": publication_info.get("journal_volume", ""),
            "journal_title": publication_info.get("journal_title", ""),
            "journal_issue": publication_info.get("journal_issue", ""),
            "page_start": publication_info.get("page_start", ""),
            "page_end": publication_info.get("page_end", ""),
            "artid": publication_info.get("artid", ""),
            "volume_year": publication_info.get("year"),
            "journal_issue_date": publication_info.get("journal_issue_date"),
            "publisher_id": publishers[idx].id,
        }
        PublicationInfo.objects.get_or_create(**publication_info_data)


def _create_experimental_collaborations(data):
    if "collaborations" in data.keys():
        for experimental_collaboration in data.get("collaborations", []):
            experimental_collaboration_data = {
                "name": experimental_collaboration.get("value"),
                "experimental_collaboration_order": 0,
            }
            (
                experimental_collaboration,
                _,
            ) = ExperimentalCollaboration.objects.get_or_create(
                **experimental_collaboration_data
            )


def _create_author(data, article):
    authors = []
    for idx, author in enumerate(data.get("authors", [])[:MAX_AUTHORS]):
        name_match = re.match(r"(.*),(.*)", author.get("full_name", ""))
        if name_match and len(name_match.groups()) == 2:
            first_name = name_match.group(2)
            last_name = name_match.group(1)
        else:
            first_name = author.get("given_names", "")
            last_name = author.get("surname", "")
        author_data = {
            "article_id": article,
            "first_name": first_name,
            "last_name": last_name,
            "email": author.get("email", ""),
            "author_order": idx,
        }
        author_obj, _ = Author.objects.get_or_create(**author_data)
        authors.append(author_obj)
    return authors


def _create_author_identifier(data, authors):
    for idx, author in enumerate(data.get("authors", [])[:MAX_AUTHORS]):
        if "orcid" in author.keys():
            author_identifier_data = {
                "author_id": authors[idx],
                "identifier_type": "ORCID",
                "identifier_value": author.get("orcid"),
            }
            AuthorIdentifier.objects.get_or_create(**author_identifier_data)


def _create_country(affiliation):
    country = affiliation.get("country", "")
    if not country or country == "HUMAN CHECK":
        return None
    if country == "cern" or country == "CERN":
        country = "Switzerland"
    elif country == "JINR":
        country = "Russia"
    country_data = {
        "code": pycountry.countries.search_fuzzy(country)[0].alpha_2,
        "name": pycountry.countries.search_fuzzy(country)[0].name,
    }
    country_obj, _ = Country.objects.get_or_create(**country_data)
    return country_obj


def _create_affiliation(data):
    for author in data.get("authors", [])[:MAX_AUTHORS]:
        for affiliation in author.get("affiliations", []):
            country = _create_country(affiliation)
            if country is not None:
                country = country.code
            affiliation_data = {
                "country_id": country,
                "value": affiliation.get("value", "")[:255],
                "organization": affiliation.get("organization", ""),
            }
            Affiliation.objects.get_or_create(**affiliation_data)


def _create_institution_identifier(data, affiliation):
    # TODO Maybe fill with something
    pass


def import_to_scoap3(data):
    licenses = _create_licenses(data["license"])
    article = _create_article(data, licenses)
    _create_article_identifier(data, article)
    _create_copyright(data, article)
    _create_article_arxiv_category(data, article)
    publishers = _create_publisher(data)
    _create_publication_info(data, article, publishers)
    _create_experimental_collaborations(data)

    authors = _create_author(data, article)
    _create_affiliation(data)
    _create_author_identifier(data, authors)


class Command(BaseCommand):
    help = "Load records into scoap3"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--path",
            type=str,
            required=True,
            help="Directory of the legacy_records version",
        )

    def handle(self, *args, **options):
        storage = storages["legacy-records"]

        amount_total = len(storage.listdir(options["path"])[1])
        for filename in storage.listdir(options["path"])[1]:
            print(filename)
            if storage.exists(os.path.join(options["path"], filename)):
                with storage.open(os.path.join(options["path"], filename)) as file:
                    json_data = json.load(file)
                    import_to_scoap3(json_data)
                    self.stdout.write(
                        f"Created ID {json_data.get('control_number')}, {1+1}/{amount_total}"
                    )