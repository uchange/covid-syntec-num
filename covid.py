import requests
import os
from flask import Flask, render_template
from flask_caching import Cache


TOKEN = os.environ.get('TOKEN')
URL = os.environ.get('URL')
WS_FAMILLE, WS_TRAVAIL, WS_SANTE, WS_SANTE_PRO = (
    os.environ.get('WS_FAMILLE'),
    os.environ.get('WS_TRAVAIL'),
    os.environ.get('WS_SANTE'),
    os.environ.get('WS_SANTE_PRO'),
)

config = {
    'CACHE_TYPE': os.environ.get('CACHE_TYPE', 'filesystem'),
    'CACHE_DIR': os.environ.get('CACHE_DIR', './cache/'),
    'CACHE_DEFAULT_TIMEOUT': int(os.environ.get('CACHE_TIMEOUT', 300)),
}
app = application = Flask(__name__)
app.config.from_mapping(config)
cache = Cache(app)


def get_startups(workspace):
    session = requests.Session()
    session.headers.update({'Authorization': f'Token {TOKEN}'})

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
        )),
        links__workspace_id=workspace,
        order_by='name',
        all=1,
    )).json()
    startups = {}
    for result in results:
        startups[result['id']] = result
        if not result['logo']:
            continue
        result['logo'] = "/".join([URL, 'media', result['logo']])

    for type in ('activity', 'entity'):
        results = session.get(URL + f'/api/startup{type}/', params=dict(
            fields=','.join((
                'startup_id',
                f'{type}__name_en',
                f'{type}__color',
            )),
            startup__links__workspace_id=workspace,
            order_by=','.join((
                'startup__name',
                f'{type}__name_en',
            )),
            all=1,
        )).json()
        for result in results:
            startup = startups[result['startup_id']]
            element = startup.setdefault(type, [])
            element.append(result)

    results = session.get(URL + '/api/linkedin/', params=dict(
        fields=','.join((
            'company_id',
            'url',
        )),
        company__startup__links__workspace_id=workspace,
        order_by=','.join((
            'company__name',
        )),
        all=1,
    )).json()
    for result in results:
        startup = startups[result['company_id']]
        element = startup.setdefault('linkedin', [])
        element.append(result)

    results = session.get(URL + '/api/twitter/', params=dict(
        fields=','.join((
            'company_id',
            'username',
        )),
        account_active=True,
        company__startup__links__workspace_id=workspace,
        order_by=','.join((
            'company__name',
        )),
        all=1,
    )).json()
    for result in results:
        startup = startups[result['company_id']]
        element = startup.setdefault('twitter', [])
        element.append(result)

    return startups.values()


@app.route('/')
@cache.cached()
def about():
    return render_template('about.html', page='about')


@app.route('/famille/')
@cache.cached()
def famille():
    startups = get_startups(WS_FAMILLE)
    return render_template('main.html', page='famille', startups=startups)


@app.route('/travail/')
@cache.cached()
def travail():
    startups = get_startups(WS_TRAVAIL)
    return render_template('main.html', page='travail', startups=startups)


@app.route('/sante/')
@cache.cached()
def sante():
    startups = get_startups(WS_SANTE)
    return render_template('main.html', page='sante', startups=startups)


@app.route('/sante-pro/')
@cache.cached()
def sante_pro():
    startups = get_startups(WS_SANTE_PRO)
    return render_template('main.html', page='sante-pro', startups=startups)
