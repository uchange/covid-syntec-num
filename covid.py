import json
import logging
import os
import requests
from urllib.parse import quote_plus

from flask import Flask, abort, render_template, request
from flask_caching import Cache
from flask_sitemap import Sitemap


URL = os.environ.get('URL')
TOKEN = os.environ.get('TOKEN')
GOOGLE_TOKEN = os.environ.get('GOOGLE_TOKEN')
HEADERS = {'Authorization': f'Token {TOKEN}'}
WORKSPACES = {
    'famille': os.environ.get('WS_FAMILLE'),
    'travail': os.environ.get('WS_TRAVAIL'),
    'sante': os.environ.get('WS_SANTE'),
    'sante-pro': os.environ.get('WS_SANTE_PRO'),
    'securite': os.environ.get('WS_SECURITE'),
}

CACHE_TYPE = os.environ.get('CACHE_TYPE', 'filesystem')
CACHE_DIR = os.environ.get('CACHE_DIR', './cache/')
CACHE_TIMEOUT = int(os.environ.get('CACHE_TIMEOUT', 900))
CACHE_SECRET = os.environ.get('CACHE_SECRET')
config = {
    'CACHE_TYPE': CACHE_TYPE,
    'CACHE_DIR': CACHE_DIR,
    'CACHE_DEFAULT_TIMEOUT': CACHE_TIMEOUT,
    'SITEMAP_URL_SCHEME': 'https',
}
app = application = Flask(__name__)
app.config.from_mapping(config)
cache, sitemap = Cache(app), Sitemap(app)

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(os.environ.get('LOGLEVEL', 'INFO'))


def get_startups(workspace=None, category=None, search=None, startup_id=None):
    """
    Get startups from Motherbase with activities, entity types, linkedin and twitter accounts
    """
    results = {}
    cache_file = os.path.join(CACHE_DIR, f'.startups_{workspace or "all"}_{category or "all"}.json')
    try:
        workspaces = ','.join([workspace] if workspace else WORKSPACES.values())
        if search:
            terms = quote_plus(search)
            search = dict(
                distinct='company__name',
                filters=(
                    f'or(company__name__unaccent__icontains:{terms},'
                    f'company__startup__value_proposition_fr__unaccent__icontains:{terms},'
                    f'extra_data__offrecovid__icontains:{terms})'
                ))
        elif startup_id:
            search = dict(
                distinct='company__name',
                company_id=startup_id,
            )
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
                    'company__startup__lat',
                    'company__startup__lng',
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
                results[result['company_id']] = result
                if not result['company__logo']:
                    continue
                result['company__logo'] = "/".join([URL, 'media', result['company__logo']])
            startup_ids = ','.join(map(str, results.keys()))
            # Activities and entity types
            if results:
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
                    if search and startup_ids:
                        params.update(startup_id__in=startup_ids)
                    else:
                        params.update(startup__links__workspace_id__in=workspaces)
                    response = session.get(URL + f'/api/startup{type}/', params=params)
                    logger.debug(f"[{response.elapsed}] {response.url}")
                    for result in response.json():
                        startup = results.get(result['startup_id'])
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
                if search and startup_ids:
                    params.update(company_id__in=startup_ids)
                else:
                    params.update(company__links__workspace_id__in=workspaces)
                response = session.get(URL + '/api/linkedin/', params=params)
                logger.debug(f"[{response.elapsed}] {response.url}")
                for result in response.json():
                    startup = results.get(result['company_id'])
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
                if search and startup_ids:
                    params.update(company_id__in=startup_ids)
                else:
                    params.update(company__links__workspace_id__in=workspaces)
                response = session.get(URL + '/api/twitter/', params=params)
                logger.debug(f"[{response.elapsed}] {response.url}")
                for result in response.json():
                    startup = results.get(result['company_id'])
                    if not startup:
                        continue
                    element = startup.setdefault('twitter', [])
                    element.append(result)
        # Save results in cache
        if not search:
            with open(cache_file, 'w') as file:
                json.dump(results, file)
    except:  # noqa
        if search or not os.path.exists(cache_file):
            return None
        # Get results from cache
        with open(cache_file, 'r') as file:
            results = json.load(file)
    # Return results
    return next(iter(results.values()), None) if startup_id else list(results.values())


def get_categories(workspace=None):
    """
    Get categories of a workspace
    """
    results = {}
    cache_file = os.path.join(CACHE_DIR, f'.categories_{workspace or "all"}.json')
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
                    results = categories
                    break
                results[str(result['workspace_id'])] = categories
        # Save results in cache
        with open(cache_file, 'w') as file:
            json.dump(results, file)
    except:  # noqa
        if not os.path.exists(cache_file):
            return None
        # Get results from cache
        with open(cache_file, 'r') as file:
            results = json.load(file)
    return results


def get_counts(workspace=None):
    """
    Get counts of startups for all workspaces and eventually a targetted one
    """
    results = {}
    results['counts'], results['subcounts'] = counts, subcounts = {}, {}
    cache_file = os.path.join(CACHE_DIR, f'.counts_{workspace or "all"}.json')
    try:
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
        # Save results in cache
        with open(cache_file, 'w') as file:
            json.dump(results, file)
    except:
        if not os.path.exists(cache_file):
            return None
        # Get results from cache
        with open(cache_file, 'r') as file:
            results = json.load(file)
    return results['counts'], results['subcounts']


@app.route('/')
@cache.cached()
def about():
    counts, subcounts = get_counts()
    return render_template(
        'about.html', page='about', subpage=None,
        counts=counts, subcounts=subcounts)


@app.route('/page/<page>/')
@app.route('/page/<page>/<category>/')
@cache.cached()
def getpage(page=None, category=None):
    workspace = WORKSPACES.get(page)
    if not workspace:
        abort(404)
    search = request.args.get('q')
    startups = get_startups(workspace, category, search)
    categories = get_categories(workspace)
    counts, subcounts = get_counts(workspace)
    return render_template(
        'main.html', page=page, subpage=category,
        counts=counts, subcounts=subcounts,
        startups=startups, categories=categories)


@app.route('/map/')
@app.route('/map/<page>/')
@app.route('/map/<page>/<category>/')
@cache.cached()
def getmap(page=None, category=None):
    search = request.args.get('q')
    if page and page != 'search':
        workspace = WORKSPACES.get(page)
        if not workspace:
            abort(404)
        counts, subcounts = get_counts(workspace)
        startups = get_startups(workspace, category, search)
    else:
        counts, subcounts = get_counts()
        startups = get_startups(search=search)
    startups = [{
        'id': startup['company_id'],
        'name': startup['company__name'],
        'lat': startup['company__startup__lat'],
        'lng': startup['company__startup__lng'],
    } for startup in startups]
    startups = json.dumps(startups)
    return render_template(
        'map.html', page=page, subpage=None,
        counts=counts, subcounts=subcounts,
        startups=startups, token=GOOGLE_TOKEN)


@app.route('/search/')
def search():
    counts, subcounts = get_counts()
    search = request.args.get('q')
    startups = get_startups(search=search) if search else {}
    return render_template(
        'search.html', page='search', subpage=None, search=True,
        counts=counts, subcounts=subcounts, startups=startups)


@app.route('/info/<startup_id>/')
def info(startup_id):
    startup = get_startups(startup_id=startup_id)
    if not startup:
        return abort(404)
    return render_template(
        'startup.html', page='info', subpage=None,
        startup=startup, popup=True)


@app.route('/cache/')
def cache():
    counts, subcounts = get_counts()
    secret = request.args.get('clear')
    files = sorted(os.listdir(CACHE_DIR))
    if secret == CACHE_SECRET:
        for file in files:
            os.remove(os.path.join(CACHE_DIR, file))
    return render_template(
        'cache.html', page='cache', subpage=None,
        counts=counts, subcounts=subcounts, files=files)


@sitemap.register_generator
def sitemap():
    yield 'about', {}
    yield 'search', {}
    categories = get_categories()
    for page, workspace in WORKSPACES.items():
        yield 'getpage', dict(page=page)
        yield 'getmap', dict(page=page)
        for category in categories.get(workspace, []):
            yield 'getpage', dict(page=page, category=category['key'])
            yield 'getmap', dict(page=page, category=category['key'])
