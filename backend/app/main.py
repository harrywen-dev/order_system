import os
from datetime import datetime, timezone, date
from decimal import Decimal
from zoneinfo import ZoneInfo
from typing import Annotated
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import create_engine, String, ForeignKey, UniqueConstraint, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker, Session

engine = create_engine(os.getenv("DATABASE_URL", "sqlite:///./lunch.db"))
SessionLocal = sessionmaker(engine)
class Base(DeclarativeBase): pass
class Day(Base):
    __tablename__ = "days"
    id: Mapped[int] = mapped_column(primary_key=True)
    lunch_date: Mapped[str] = mapped_column(String, unique=True)
    interest_end: Mapped[str]
    vote_end: Mapped[str]
class Proposal(Base):
    __tablename__ = "proposals"
    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("days.id"))
    author: Mapped[str]
    restaurant: Mapped[str]
    link: Mapped[str]
    minimum: Mapped[int]
    menu: Mapped[str]
    order_open: Mapped[str]
    order_end: Mapped[str]
class Interest(Base):
    __tablename__ = "interests"
    __table_args__ = (UniqueConstraint("proposal_id", "employee"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    employee: Mapped[str]
    quantity: Mapped[int]
class Vote(Base):
    __tablename__ = "votes"
    __table_args__ = (UniqueConstraint("day_id", "employee"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    day_id: Mapped[int] = mapped_column(ForeignKey("days.id"))
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    employee: Mapped[str]
class Order(Base):
    __tablename__ = "orders"
    __table_args__ = (UniqueConstraint("proposal_id", "employee"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    proposal_id: Mapped[int] = mapped_column(ForeignKey("proposals.id"))
    employee: Mapped[str]
    item: Mapped[str]
    quantity: Mapped[int]
    price: Mapped[str]
    note: Mapped[str]
Base.metadata.create_all(engine)
app = FastAPI(title="員工午餐團購")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_methods=["*"], allow_headers=["*"])
def db():
    with SessionLocal() as session: yield session
DB = Annotated[Session, Depends(db)]
def now(): return datetime.now(timezone.utc)
def instant(value): return datetime.fromisoformat(value)
def fail(message): raise HTTPException(400, message)
def get(s, model, id):
    obj=s.get(model,id)
    if obj is None: raise HTTPException(404,"找不到資料")
    return obj
class Identity(BaseModel):
    employee: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
class ProposalIn(BaseModel):
    author: str = Field(min_length=1, max_length=80, pattern=r".*\S.*")
    lunch_date: date
    restaurant: str = Field(min_length=1, max_length=120, pattern=r".*\S.*")
    link: str = Field(pattern=r"^https?://[^\s]+$", max_length=1000)
    minimum: int = Field(ge=1,le=10000)
    menu: str = Field(min_length=1,max_length=20000)
    interest_end: datetime
    vote_end: datetime
    order_open: datetime
    order_end: datetime
    @model_validator(mode="after")
    def times(self):
        ts=[self.interest_end,self.vote_end,self.order_open,self.order_end]
        if any(t.tzinfo is None for t in ts): raise ValueError("時間必須含時區")
        if not self.interest_end < self.vote_end <= self.order_open < self.order_end: raise ValueError("時間順序須為募集截止、投票截止、點餐開啟、點餐截止")
        return self
class InterestIn(Identity): quantity: int = Field(ge=0,le=100)
class OrderIn(Identity):
    item: str = Field(min_length=1,max_length=200,pattern=r".*\S.*")
    quantity: int = Field(ge=1,le=100)
    price: Decimal = Field(ge=0,le=100000,max_digits=10,decimal_places=2)
    note: str = Field(default="",max_length=1000)
def state(s,day):
    ps=list(s.scalars(select(Proposal).where(Proposal.day_id==day.id).order_by(Proposal.id)))
    totals={p.id:sum(i.quantity for i in s.scalars(select(Interest).where(Interest.proposal_id==p.id))) for p in ps}
    qualified=[p for p in ps if totals[p.id]>=p.minimum]
    votes={p.id:len(list(s.scalars(select(Vote).where(Vote.proposal_id==p.id)))) for p in ps}
    t=now(); winner=None
    if t<instant(day.interest_end): phase="募集意願"
    elif not qualified: phase="未達門檻"
    elif len(qualified)>1 and t<instant(day.vote_end): phase="投票中"
    else:
        # Ties (including zero votes) resolve deterministically to the earliest proposal.
        winner=max(qualified,key=lambda p:(votes[p.id],-p.id)) if len(qualified)>1 else qualified[0]
        phase="等待點餐" if t<instant(winner.order_open) else "點餐中" if t<instant(winner.order_end) else "已截止"
    return ps,totals,votes,qualified,winner,phase
@app.get("/api/health")
def health(s:DB):
    s.execute(select(Day).limit(1)); return {"status":"ok"}
@app.get("/api/days")
def days(s:DB):
    result=[]
    for d in s.scalars(select(Day).order_by(Day.lunch_date.desc())):
        ps,totals,votes,qualified,winner,phase=state(s,d)
        result.append(dict(id=d.id,lunch_date=d.lunch_date,interest_end=d.interest_end,vote_end=d.vote_end,phase=phase,winner_id=winner.id if winner else None,proposals=[dict(id=p.id,author=p.author,restaurant=p.restaurant,link=p.link,minimum=p.minimum,menu=p.menu,order_open=p.order_open,order_end=p.order_end,interest_quantity=totals[p.id],votes=votes[p.id],qualified=p in qualified) for p in ps]))
    return result
@app.post("/api/proposals",status_code=201)
def proposal(data:ProposalIn,s:DB):
    if data.interest_end<=now(): fail("募集截止時間必須在未來")
    if data.lunch_date<now().astimezone(ZoneInfo("Asia/Taipei")).date(): fail("用餐日期不可在過去")
    # Serialize creation for a date on PostgreSQL, including first-day creation.
    if engine.dialect.name=="postgresql":
        from sqlalchemy import text
        s.execute(text("SELECT pg_advisory_xact_lock(:key)"),{"key":data.lunch_date.toordinal()})
    d=s.scalar(select(Day).where(Day.lunch_date==str(data.lunch_date)))
    if d:
        if now()>=instant(d.interest_end): fail("當日募集已截止")
        if instant(d.interest_end)!=data.interest_end or instant(d.vote_end)!=data.vote_end: fail("同日提案須使用既有募集與投票截止時間")
    else:
        d=Day(lunch_date=str(data.lunch_date),interest_end=data.interest_end.isoformat(),vote_end=data.vote_end.isoformat());s.add(d);s.flush()
    p=Proposal(day_id=d.id,**data.model_dump(exclude={"lunch_date","interest_end","vote_end","order_open","order_end"}),order_open=data.order_open.isoformat(),order_end=data.order_end.isoformat())
    s.add(p);s.commit();return {"id":p.id}
@app.put("/api/proposals/{id}/interest")
def interest(id:int,data:InterestIn,s:DB):
    p=get(s,Proposal,id);d=s.scalar(select(Day).where(Day.id==p.day_id).with_for_update())
    if now()>=instant(d.interest_end): fail("意願募集已截止")
    i=s.scalar(select(Interest).where(Interest.proposal_id==id,Interest.employee==data.employee))
    if i: i.quantity=data.quantity
    else: s.add(Interest(proposal_id=id,**data.model_dump()))
    s.commit();return {"ok":True}
@app.put("/api/proposals/{id}/vote")
def vote(id:int,data:Identity,s:DB):
    p=get(s,Proposal,id);d=s.scalar(select(Day).where(Day.id==p.day_id).with_for_update())
    _,_,_,qs,_,phase=state(s,d)
    if phase!="投票中" or p not in qs: fail("目前不可投票給此店家")
    v=s.scalar(select(Vote).where(Vote.day_id==d.id,Vote.employee==data.employee))
    if v: v.proposal_id=id
    else: s.add(Vote(day_id=d.id,proposal_id=id,employee=data.employee))
    s.commit();return {"ok":True}
@app.put("/api/proposals/{id}/order")
def order(id:int,data:OrderIn,s:DB):
    p=get(s,Proposal,id);d=s.scalar(select(Day).where(Day.id==p.day_id).with_for_update())
    _,_,_,_,winner,phase=state(s,d)
    if phase!="點餐中" or winner.id!=id: fail("此店家未開放點餐或已截止")
    o=s.scalar(select(Order).where(Order.proposal_id==id,Order.employee==data.employee))
    values=data.model_dump();values["price"]=str(data.price)
    if o:
        for k,v in values.items(): setattr(o,k,v)
    else: s.add(Order(proposal_id=id,**values))
    s.commit();return {"ok":True}
@app.get("/api/proposals/{id}/orders")
def summary(id:int,s:DB):
    p=get(s,Proposal,id)
    rows=list(s.scalars(select(Order).where(Order.proposal_id==id).order_by(Order.id)))
    quantity=sum(o.quantity for o in rows)
    return {"orders":[dict(employee=o.employee,item=o.item,quantity=o.quantity,price=o.price,note=o.note) for o in rows],"quantity":quantity,"total":str(sum((Decimal(o.price)*o.quantity for o in rows),Decimal(0))),"below_minimum":quantity<p.minimum}

@app.delete("/api/proposals/{id}/order")
def cancel(id:int,data:Identity,s:DB):
    p=get(s,Proposal,id);d=s.scalar(select(Day).where(Day.id==p.day_id).with_for_update())
    _,_,_,_,winner,phase=state(s,d)
    if phase!="點餐中" or winner.id!=id: fail("目前不可取消訂單")
    o=s.scalar(select(Order).where(Order.proposal_id==id,Order.employee==data.employee))
    if o: s.delete(o)
    s.commit();return {"ok":True}
