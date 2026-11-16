import json
import logging
from fastapi.testclient import TestClient


def exercise(app,caplog):
    @app.get('/api/test-error')
    def error():
        raise ValueError('do-not-log-secret-value')
    app.router.routes.insert(0,app.router.routes.pop())  # Keep test route ahead of the static mount.

    with TestClient(app,raise_server_exceptions=False) as client:
        with caplog.at_level(logging.INFO,logger='portfolio.http'):
            good=client.get('/api/ready?token=do-not-log-secret-value',headers={'Cookie':'session=do-not-log-secret-value','X-Request-ID':'do-not-log-secret-value'})
            assert good.status_code==200
            assert len(good.headers['x-request-id'])==32
            def unavailable():
                raise RuntimeError('do-not-log-secret-value')
            app.state.db_probe=unavailable
            bad=client.get('/api/ready')
            assert bad.status_code==503
            assert bad.json()=={'status':'unavailable'}
            failure=client.get('/api/test-error')
            assert failure.status_code==500
            assert failure.json()=={'detail':'Internal server error'}
            client.post('/unknown/do-not-log-secret-value',json={'password':'do-not-log-secret-value'})
        events=[json.loads(r.getMessage()) for r in caplog.records if r.name=='portfolio.http']
        assert len(events)==4
        assert events[0]['route']=='/api/ready'
        assert events[2]['error_type']=='ValueError'
        assert events[3]['route'] in {'unmatched',''}
        assert all('do-not-log-secret-value' not in json.dumps(event) for event in events)
        assert all(event['duration_ms']>=0 and 100<=event['status']<=599 for event in events)


def test_readiness_logs_and_internal_failure_redaction(tmp_path,caplog):
    from app.api import create_app
    exercise(create_app(tmp_path/'ops.sqlite'),caplog)


def test_actual_database_unavailability_returns_503(tmp_path):
    from app.api import create_app
    path=tmp_path/'missing.sqlite'
    app=create_app(path)
    with TestClient(app) as client:
        assert client.get('/api/ready').status_code==200
        path.unlink()
        assert client.get('/api/ready').status_code==503
        assert not path.exists()
