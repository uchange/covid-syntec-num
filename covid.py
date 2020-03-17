import logging
import os
import requests
import traceback

from flask import Flask, render_template
from flask_caching import Cache


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
}
app = application = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(os.environ.get('LOGLEVEL', 'INFO'))


def get_startups(workspace, category=None):
    """
    Get startups from Motherbase with activities, entity types, linkedin and twitter accounts
    """
    if not workspace:
        return {}
    try:
        startups = {}
        with requests.Session() as session:
            session.headers.update(HEADERS)
            # Startups
            results = session.get(URL + '/api/startup/', params=dict(
                fields=','.join((
                    'id',
                    'name',
                    'logo',
                    'value_proposition_fr',
                    'website_url',
                    'city',
                    'nb_employees',
                    'creation_date__year',
                    'links__extra_data',
                )),
                order_by='name',
                all=1,
                links__workspace_id=workspace,
                **(dict(links__extra_data__category=category) if category else {})
            ))
            logger.debug(f"[{results.elapsed}] {results.url}")
            for result in results.json():
                startups[result['id']] = result
                if not result['logo']:
                    continue
                result['logo'] = "/".join([URL, 'media', result['logo']])
            # Activities and entity types
            for type in ('activity', 'entity'):
                results = session.get(URL + f'/api/startup{type}/', params=dict(
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
                    startup__links__workspace_id=workspace,
                    **(dict(startup__links__extra_data__category=category) if category else {})
                ))
                logger.debug(f"[{results.elapsed}] {results.url}")
                for result in results.json():
                    startup = startups[result['startup_id']]
                    element = startup.setdefault(type, [])
                    element.append(result)
            # LinkedIn
            results = session.get(URL + '/api/linkedin/', params=dict(
                fields=','.join((
                    'company_id',
                    'url',
                )),
                order_by=','.join((
                    'company__name',
                )),
                all=1,
                company__links__workspace_id=workspace,
                **(dict(company__links__extra_data__category=category) if category else {})
            ))
            logger.debug(f"[{results.elapsed}] {results.url}")
            for result in results.json():
                startup = startups[result['company_id']]
                element = startup.setdefault('linkedin', [])
                element.append(result)
            # Twitter
            results = session.get(URL + '/api/twitter/', params=dict(
                fields=','.join((
                    'company_id',
                    'username',
                )),
                account_active=True,
                order_by=','.join((
                    'company__name',
                )),
                all=1,
                company__links__workspace_id=workspace,
                **(dict(company__links__extra_data__category=category) if category else {})
            ))
            logger.debug(f"[{results.elapsed}] {results.url}")
            for result in results.json():
                startup = startups[result['company_id']]
                element = startup.setdefault('twitter', [])
                element.append(result)
        # Return results
        return startups.values()
    except:  # noqa
        traceback.print_exc()
    return None


def get_categories(workspace):
    """
    Get categories of a workspace
    """
    if not workspace:
        return []
    try:
        with requests.Session() as session:
            session.headers.update(HEADERS)
            results = session.get(URL + '/api/front/attribute/', params=dict(
                name='category',
                workspace_id=workspace,
                all=1
            ))
            logger.debug(f"[{results.elapsed}] {results.url}")
            for result in results.json():
                return sorted(result['enum'], key=lambda e: e['value'])
    except:  # noqa
        traceback.print_exc()
    return []


def get_counts(workspace=None):
    """
    Get counts of startups for all workspaces and eventually a targetted one
    """
    try:
        counts, subcounts = {}, {}
        with requests.Session() as session:
            session.headers.update(HEADERS)
            # Counts by workspace
            results = session.get(URL + '/api/front/link', params=dict(
                workspace__in=','.join(WORKSPACES.values()),
                company__startup__isnull=False,
                group_by='workspace_id',
                count='id',
                all=1,
            ))
            logger.debug(f"[{results.elapsed}] {results.url}")
            pages = {wid: page for page, wid in WORKSPACES.items()}
            for result in results.json():
                page = pages.get(str(result['workspace_id']))
                counts[page] = result['id_count']
            # Counts by category in workspace
            if workspace:
                results = session.get(URL + '/api/front/link', params=dict(
                    workspace=workspace,
                    company__startup__isnull=False,
                    group_by='extra_data__category',
                    count='id',
                    all=1,
                ))
                logger.debug(f"[{results.elapsed}] {results.url}")
                for result in results.json():
                    subpage = result['extra_data__category']
                    subcounts[subpage] = result['id_count']
        # Return results
        return counts, subcounts
    except:
        raise
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
