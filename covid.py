import logging
import os
from urllib.parse import quote_plus

import requests
import traceback

from flask import Flask, render_template, request
from flask_caching import Cache
from flask_sitemap import Sitemap


URL = os.environ.get('URL')
TOKEN = os.environ.get('TOKEN')
HEADERS = {'Authorization': f'Token {TOKEN}'}
WORKSPACES = {
    'famille': os.environ.get('WS_FAMILLE'),
    'travail': os.environ.get('WS_TRAVAIL'),
    'sante': os.environ.get('WS_SANTE'),
    'sante_pro': os.environ.get('WS_SANTE_PRO'),
}

config = {
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'filesystem'),
    'CACHE_DIR': os.environ.get('CACHE_DIR', './cache/'),
    'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_TIMEOUT', 900)),
    'SITEMAP_URL_SCHEME': 'https',
}
app = application = Flask(__name__)
app.config.from_mapping(config)
cache, sitemap = Cache(app), Sitemap(app)

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(os.environ.get('LOGLEVEL', 'INFO'))


def get_startups(workspace=None, category=None, search=None):
    """
    Get startups from Motherbase with activities, entity types, linkedin and twitter accounts
    """
    try:
        startups = {}
        workspaces = ','.join([workspace] if workspace else WORKSPACES.values())
        if search:
            terms = quote_plus(search)
            search = dict(
                distinct='company__name',
                filters=(
                    f'or(company__name__unaccent__icontains:{terms},'
                    f'company__startup__value_proposition_fr__unaccent__icontains:{terms},'
                    f'extra_data__offrecovid__unaccent__icontains:{terms})'
                ))
        with requests.Session() as session:
            session.headers.update(HEADERS)
            # Startups
            params = dict(
                fields=','.join((
                    'company_id',
                    'company__name',
                    'company__logo',
                    'company__website_url',
                    'company__nb_employees',
                    'company__startup__value_proposition_fr',
                    'company__startup__city',
                    'company__startup__creation_date__year',
                    'extra_data',
                )),
                company__startup__isnull=0,
                order_by='company__name',
                all=1,
                workspace_id__in=workspaces,
            )
            if category:
                params.update(extra_data__category=category)
            if search:
                params.update(search)
            response = session.get(URL + '/api/front/link/', params=params)
            logger.debug(f"[{response.elapsed}] {response.url}")
            for result in response.json():
                startups[result['company_id']] = result
                if not result['company__logo']:
                    continue
                result['company__logo'] = "/".join([URL, 'media', result['company__logo']])
            startup_ids = ','.join(map(str, startups.keys()))
            # Activities and entity types
            if startups:
                for type in ('activity', 'entity'):
                    params = dict(
                        fields=','.join((
                            'startup_id',
                            f'{type}__name_en',
                            f'{type}__color',
                        )),
                        order_by=','.join((
                            'startup__name',
                            f'{type}__name_en',
                        )),
                        all=1,
                    )
                    if category:
                        params.update(startup__links__extra_data__category=category)
                    if search:
                        params.update(startup_id__in=startup_ids)
                    else:
                        params.update(startup__links__workspace_id__in=workspaces)
                    response = session.get(URL + f'/api/startup{type}/', params=params)
                    logger.debug(f"[{response.elapsed}] {response.url}")
                    for result in response.json():
                        startup = startups.get(result['startup_id'])
                        if not startup:
                            continue
                        element = startup.setdefault(type, [])
                        element.append(result)
                # LinkedIn
                params = dict(
                    fields=','.join((
                        'company_id',
                        'url',
                    )),
                    order_by=','.join((
                        'company__name',
                    )),
                    all=1,
                )
                if category:
                    params.update(company__links__extra_data__category=category)
                if search:
                    params.update(company_id__in=startup_ids)
                else:
                    params.update(company__links__workspace_id__in=workspaces)
                response = session.get(URL + '/api/linkedin/', params=params)
                logger.debug(f"[{response.elapsed}] {response.url}")
                for result in response.json():
                    startup = startups.get(result['company_id'])
                    if not startup:
                        continue
                    element = startup.setdefault('linkedin', [])
                    element.append(result)
                # Twitter
                params = dict(
                    fields=','.join((
                        'company_id',
                        'username',
                    )),
                    account_active=True,
                    order_by=','.join((
                        'company__name',
                    )),
                    all=1,
                )
                if category:
                    params.update(company__links__extra_data__category=category)
                if search:
                    params.update(company_id__in=startup_ids)
                else:
                    params.update(company__links__workspace_id__in=workspaces)
                response = session.get(URL + '/api/twitter/', params=params)
                logger.debug(f"[{response.elapsed}] {response.url}")
                for result in response.json():
                    startup = startups.get(result['company_id'])
                    if not startup:
                        continue
                    element = startup.setdefault('twitter', [])
                    element.append(result)
        # Return results
        return startups.values()
    except:  # noqa
        traceback.print_exc()
    return None


def get_categories(workspace=None):
    """
    Get categories of a workspace
    """
    results = {}
    if not workspace:
        return results
    try:
        workspaces = ','.join([workspace] if workspace else WORKSPACES.values())
        with requests.Session() as session:
            session.headers.update(HEADERS)
            response = session.get(URL + '/api/front/attribute/', params=dict(
                name='category',
                workspace_id__in=workspaces,
                all=1,
            ))
            logger.debug(f"[{response.elapsed}] {response.url}")
            # Return results
            for result in response.json():
                categories = sorted(result['enum'], key=lambda e: e['value'])
                if workspace:
                    return categories
                results[str(result['workspace_id'])] = categories
            return results
    except:  # noqa
        traceback.print_exc()
    return results


def get_counts(workspace=None):
    """
    Get counts of startups for all workspaces and eventually a targetted one
    """
    try:
        counts, subcounts = {}, {}
        with requests.Session() as session:
            session.headers.update(HEADERS)
            # Counts by workspace
            response = session.get(URL + '/api/front/link', params=dict(
                workspace__in=','.join(WORKSPACES.values()),
                company__startup__isnull=False,
                group_by='workspace_id',
                count='id',
                all=1,
            ))
            logger.debug(f"[{response.elapsed}] {response.url}")
            pages = {wid: page for page, wid in WORKSPACES.items()}
            for result in response.json():
                page = pages.get(str(result['workspace_id']))
                counts[page] = result['id_count']
            # Counts by category in workspace
            if workspace:
                response = session.get(URL + '/api/front/link', params=dict(
                    workspace=workspace,
                    company__startup__isnull=False,
                    group_by='extra_data__category',
                    count='id',
                    all=1,
                ))
                logger.debug(f"[{response.elapsed}] {response.url}")
                for result in response.json():
                    subpage = result['extra_data__category']
                    subcounts[subpage] = result['id_count']
        # Return results
        return counts, subcounts
    except:
        return {}, {}


def get_page(page, category=None):
    """
    Shortcut to return a page of startups given a page name and a category
    """
    workspace = WORKSPACES.get(page)
    startups = get_startups(workspace, category)
    categories = get_categories(workspace)
    counts, subcounts = get_counts(workspace)
    return render_template(
        'main.html', page=page, subpage=category,
        counts=counts, subcounts=subcounts,
        startups=startups, categories=categories)


@app.route('/')
@cache.cached()
def about():
    counts, subcounts = get_counts()
    return render_template('about.html', page='about', counts=counts)


@app.route('/famille/')
@app.route('/famille/<category>/')
@cache.cached()
def famille(category=None):
    return get_page('famille', category)


@app.route('/travail/')
@app.route('/travail/<category>/')
@cache.cached()
def travail(category=None):
    return get_page('travail', category)


@app.route('/sante/')
@app.route('/sante/<category>/')
@cache.cached()
def sante(category=None):
    return get_page('sante', category)


@app.route('/sante-pro/')
@app.route('/sante-pro/<category>/')
@cache.cached()
def sante_pro(category=None):
    return get_page('sante_pro', category)


@app.route('/recherche/')
def search():
    counts, subcounts = get_counts()
    search = request.args.get('q')
    startups = get_startups(search=search) if search else {}
    return render_template(
        'search.html', page='search',
        counts=counts, subcounts=subcounts,
        startups=startups)


@sitemap.register_generator
def sitemap():
    categories = get_categories()
    for page, workspace in WORKSPACES.items():
        yield page, {}
        for category in categories.get(workspace, []):
            yield page, dict(category=category['key'])
