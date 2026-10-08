import os
os.environ['DATABASE_URL']='sqlite://'
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from app import main as m

@pytest.fixture
def setup(monkeypatch):
    test_url=os.getenv('TEST_DATABASE_URL')
    engine=create_engine(test_url) if test_url else create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    if test_url: m.Base.metadata.drop_all(engine)
    m.Base.metadata.create_all(engine)
    monkeypatch.setattr(m,'engine',engine)
    monkeypatch.setattr(m,'SessionLocal',sessionmaker(engine))
    clock=[datetime(2030,1,1,0,tzinfo=timezone.utc)]
    monkeypatch.setattr(m,'now',lambda:clock[0])
    return TestClient(m.app),clock

def proposal(c,restaurant='A',minimum=3):
    r=c.post('/api/proposals',json=dict(author='Amy',lunch_date='2030-01-01',restaurant=restaurant,link='https://example.com',minimum=minimum,menu='便當 100',interest_end='2030-01-01T01:00:00Z',vote_end='2030-01-01T02:00:00Z',order_open='2030-01-01T02:00:00Z',order_end='2030-01-01T03:00:00Z'))
    assert r.status_code==201,r.text
    return r.json()['id']
def test_multiple_restaurants_vote_and_order(setup):
    c,t=setup;a=proposal(c);b=proposal(c,'B')
    for p in [a,b]: assert c.put(f'/api/proposals/{p}/interest',json={'employee':'Amy','quantity':3}).status_code==200
    assert c.put(f'/api/proposals/{a}/vote',json={'employee':'Amy'}).status_code==400
    t[0]+=timedelta(hours=1)
    assert c.get('/api/days').json()[0]['phase']=='投票中'
    assert c.put(f'/api/proposals/{a}/vote',json={'employee':'Amy'}).status_code==200
    assert c.put(f'/api/proposals/{b}/vote',json={'employee':'Amy'}).status_code==200
    day=c.get('/api/days').json()[0]
    assert [p['votes'] for p in day['proposals']]==[0,1]
    assert c.put(f'/api/proposals/{a}/interest',json={'employee':'Amy','quantity':4}).status_code==400
    t[0]+=timedelta(hours=1)
    data={'employee':'Amy','item':'便當','quantity':2,'price':'100.50'}
    assert c.put(f'/api/proposals/{a}/order',json=data).status_code==400
    assert c.put(f'/api/proposals/{b}/order',json=data).status_code==200
    summary=c.get(f'/api/proposals/{b}/orders').json()
    assert summary['total']=='201.00' and summary['below_minimum']
    data['quantity']=3
    assert c.put(f'/api/proposals/{b}/order',json=data).status_code==200
    assert c.get(f'/api/proposals/{b}/orders').json()['quantity']==3
    t[0]+=timedelta(hours=1)
    assert c.put(f'/api/proposals/{b}/order',json=data).status_code==400
    assert c.get('/api/days').json()[0]['phase']=='已截止'
def test_single_qualified_and_withdrawal(setup):
    c,t=setup;a=proposal(c);b=proposal(c,'B')
    c.put(f'/api/proposals/{a}/interest',json={'employee':'Amy','quantity':3})
    c.put(f'/api/proposals/{b}/interest',json={'employee':'Amy','quantity':3})
    c.put(f'/api/proposals/{b}/interest',json={'employee':'Amy','quantity':0})
    t[0]+=timedelta(hours=1)
    day=c.get('/api/days').json()[0]
    assert day['winner_id']==a and day['phase']=='等待點餐'
def test_no_qualified_and_input_validation(setup):
    c,t=setup;a=proposal(c)
    assert c.put(f'/api/proposals/{a}/interest',json={'employee':'Amy','quantity':-1}).status_code==422
    assert c.put(f'/api/proposals/{a}/interest',json={'employee':' ','quantity':1}).status_code==422
    t[0]+=timedelta(hours=1)
    assert c.get('/api/days').json()[0]['phase']=='未達門檻'
def test_tie_earliest_proposal(setup):
    c,t=setup;a=proposal(c);b=proposal(c,'B')
    for p in [a,b]: c.put(f'/api/proposals/{p}/interest',json={'employee':'Amy','quantity':3})
    t[0]+=timedelta(hours=2)
    assert c.get('/api/days').json()[0]['winner_id']==a

def test_cancel_and_shared_deadlines(setup):
    c,t=setup;a=proposal(c)
    c.put(f'/api/proposals/{a}/interest',json={'employee':'Amy','quantity':3})
    body=dict(author='Ben',lunch_date='2030-01-01',restaurant='B',link='https://example.com',minimum=2,menu='飯',interest_end='2030-01-01T01:30:00Z',vote_end='2030-01-01T02:00:00Z',order_open='2030-01-01T02:00:00Z',order_end='2030-01-01T03:00:00Z')
    assert c.post('/api/proposals',json=body).status_code==400
    t[0]+=timedelta(hours=2)
    assert c.put(f'/api/proposals/{a}/order',json={'employee':'Amy','item':'飯','quantity':3,'price':'100'}).status_code==200
    assert c.request('DELETE',f'/api/proposals/{a}/order',json={'employee':'Amy'}).status_code==200
    assert c.get(f'/api/proposals/{a}/orders').json()['quantity']==0
    t[0]+=timedelta(hours=1)
    assert c.request('DELETE',f'/api/proposals/{a}/order',json={'employee':'Amy'}).status_code==400
