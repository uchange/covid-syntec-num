import os
import requests
import traceback

from flask import Flask, render_template
from flask_caching import Cache


URL = os.environ.get('URL')
TOKEN = os.environ.get('TOKEN')
TRACE = bool(os.environ.get('TRACE'))
WS_FAMILLE, WS_TRAVAIL, WS_SANTE, WS_SANTE_PRO = (
    os.environ.get('WS_FAMILLE'),
    os.environ.get('WS_TRAVAIL'),
    os.environ.get('WS_SANTE'),
    os.environ.get('WS_SANTE_PRO'),
)

config = {
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'filesystem'),
    'CACHE_DIR': os.environ.get('CACHE_DIR', './cache/'),
    'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_TIMEOUT', 900)),
}
app = application = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)


def get_startups(workspace, category=None):
    try:
        with requests.Session() as session:
            session.headers.update({
                'Authorization': f'Token {TOKEN}',
            })
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
            print(f"[{results.elapsed}] {results.url}") if TRACE else None
            startups = {}
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
                print(f"[{results.elapsed}] {results.url}") if TRACE else None
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
            print(f"[{results.elapsed}] {results.url}") if TRACE else None
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
            print(f"[{results.elapsed}] {results.url}") if TRACE else None
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
    try:
        with requests.Session() as session:
            session.headers.update({
                'Authorization': f'Token {TOKEN}',
            })
            results = session.get(URL + '/api/front/attribute/', params=dict(
                name='category',
                workspace_id=workspace,
                all=1
            )).json()
            for result in results:
                return sorted(result['enum'], key=lambda e: e['value'])
    except:  # noqa
        traceback.print_exc()
    return []



@app.route('/')
@cache.cached()
def about():
    return render_template('about.html', page='about')


@app.route('/famille/')
@app.route('/famille/<category>/')
@cache.cached()
def famille(category=None):
    startups = get_startups(WS_FAMILLE, category)
    categories = get_categories(WS_FAMILLE)
    return render_template(
        'main.html', page='famille', subpage=category,
        startups=startups, categories=categories)


@app.route('/travail/')
@app.route('/travail/<category>/')
@cache.cached()
def travail(category=None):
    startups = get_startups(WS_TRAVAIL, category)
    categories = get_categories(WS_TRAVAIL)
    return render_template(
        'main.html', page='travail', subpage=category,
        startups=startups, categories=categories)


@app.route('/sante/')
@app.route('/sante/<category>/')
@cache.cached()
def sante(category=None):
    startups = get_startups(WS_SANTE, category)
    categories = get_categories(WS_SANTE)
    return render_template(
        'main.html', page='sante', subpage=category,
        startups=startups, categories=categories)


@app.route('/sante-pro/')
@app.route('/sante-pro/<category>/')
@cache.cached()
def sante_pro(category=None):
    startups = get_startups(WS_SANTE_PRO, category)
    categories = get_categories(WS_SANTE_PRO)
    return render_template(
        'main.html', page='sante_pro', subpage=category,
        startups=startups, categories=categories)
