import copy
import math
import sqlite3
import pytest
from yellowstone_python.park_runtime.contracts import WorldFrame, Interest, RegionSpec, DependencyGraph
from yellowstone_python.park_runtime.coupling import Stores, FluxLedger, prolong, restrict
from yellowstone_python.park_runtime.reference_network import Reservoir, ReservoirNetwork, RHO_CP
from yellowstone_python.park_runtime.runtime import ParkRuntime
from yellowstone_python.park_runtime.state_store import StateStore
from yellowstone_python.park_runtime.forcing import ForcingTimeline

def domain(name="river"):
    return ReservoirNetwork(name,[Reservoir.at_temperature("a",1000,12,.01),
        Reservoir.at_temperature("b",400,8,.008), Reservoir.at_temperature("c",600,15,.007),
        Reservoir.at_temperature("d",2000,11,.005)],
        [("a","b",.6),("a","c",.4),("b","d",1.),("c","d",1.)],
        {"a":{"flow_m3s":10.,"temperature_c":14.,"solute_kg_m3":.02}})

def test_coordinates_roundtrip():
    frame=WorldFrame(512952.5950985841,4930199.044097667)
    p=(85555.1234,22.25,-79999.125)
    assert frame.to_local(*frame.to_projected(*p))==pytest.approx(p,abs=1e-8)

@pytest.mark.parametrize("value",[float("nan"),float("inf"),True])
def test_coordinates_reject_invalid(value):
    with pytest.raises(ValueError): WorldFrame(value,0.)

def test_hidden_dependency_closure():
    graph=DependencyGraph([RegionSpec("visible",("hidden_upstream",)),RegionSpec("hidden_upstream",("weather",)),RegionSpec("weather",always_active=True)])
    assert graph.required({"visible"})=={"visible","hidden_upstream","weather"}
    assert graph.required(set())=={"weather"}

def test_dependency_cycle_terminates():
    graph=DependencyGraph([RegionSpec("a",("b",)),RegionSpec("b",("a",))])
    assert graph.required({"a"})=={"a","b"}

def test_conservative_regrid():
    parent=Stores(123.,-156000.,.7)
    assert restrict(prolong(parent,[.1,.3,.6]))==parent
    with pytest.raises(ValueError): prolong(parent,[.1,.2])

def test_flux_exactly_once():
    ledger=FluxLedger()
    flux=Stores(3,4,5)
    assert ledger.record("a:b",0,1,flux,"one")
    assert not ledger.record("a:b",0,1,flux,"one")
    assert ledger.totals["a:b"]==flux
    with pytest.raises(ValueError): ledger.record("a:b",0,1,Stores(4,4,5),"one")
    with pytest.raises(ValueError): ledger.record("a:b",.5,2,flux,"two")
    assert ledger.record("a:b",1,2,flux,"two")

def test_branch_confluence_conservation():
    d=domain(); d.advance_to(120.)
    ledger=d.snapshot()["ledger"]
    assert abs(ledger["water_residual_m3"])<1e-8
    assert abs(ledger["heat_residual_j"])/(RHO_CP*4000*14)<1e-12
    assert abs(ledger["solute_residual_kg"])<1e-10
    assert all(n.volume_m3>0 for n in d.nodes.values())

def test_checkpoint_resume():
    a=domain(); a.advance_to(20); cp=a.checkpoint(); a.advance_to(40)
    expected=a.snapshot()
    b=domain(); b.restore(cp); b.advance_to(40)
    assert b.snapshot()==expected

def test_hidden_region_still_evolves():
    r=ParkRuntime([domain("visible"),domain("hidden")])
    r.compute_until(5)
    packet=r.packet(4.5,Interest(("visible",),1))
    assert set(packet["bracket"][0]["regions"])=={"visible"}
    assert r.domains["hidden"].time_s==5
    assert r.domains["hidden"].snapshot()["nodes"][0]["temperature_c"]!=12.

def test_interest_validation():
    assert Interest.parse({"region_ids":["a","a"],"sequence":3}).region_ids==("a",)
    for item in [{"region_ids":["../a"]},{"region_ids":["x"]*129},{"sequence":True}]:
        with pytest.raises(ValueError): Interest.parse(item)

def test_intervention_discards_future_and_replays():
    r=ParkRuntime([domain()]); r.compute_until(15)
    change={"inputs":{"a":{"flow_m3s":12.,"temperature_c":20.}}}
    event=r.intervene("event1","river",5.,change)
    assert r.time_s==5 and r.revision==1
    assert r.packet(5)["bracket"][0]["revision"]==1
    r.compute_until(15)
    expected=domain(); expected.advance_to(5); expected.intervene(change); expected.advance_to(15)
    assert r.domains["river"].snapshot()==expected.snapshot()
    assert r.intervene("event1","river",5.,change)==event
    with pytest.raises(ValueError): r.intervene("event1","river",5.,{"inputs":{}})

def test_bad_intervention_is_atomic():
    r=ParkRuntime([domain()]); r.compute_until(10)
    old=r.domains["river"].snapshot()
    with pytest.raises(ValueError): r.intervene("bad","river",5.,{"invalid":7})
    assert r.domains["river"].snapshot()==old
    assert r.time_s==10 and r.revision==0

def test_late_events_rejected():
    r=ParkRuntime([domain()]); r.compute_until(10)
    r.intervene("first","river",6.,{"inputs":{}}); r.compute_until(10)
    with pytest.raises(ValueError): r.intervene("late","river",5.,{"inputs":{}})

def test_domain_failure_rolls_back_every_domain():
    class Failing(ReservoirNetwork):
        def advance_to(self,target):
            super().advance_to(target)
            raise RuntimeError("fixture failure")
    b=domain("b"); b.__class__=Failing
    r=ParkRuntime([domain("a"),b])
    before=r.domains["a"].snapshot()
    with pytest.raises(RuntimeError): r.advance_one(1.)
    assert r.time_s==0 and r.domains["a"].snapshot()==before and b.time_s==0

def test_save_only_committed_time(tmp_path):
    store=StateStore(tmp_path/"state.db")
    r=ParkRuntime([domain()]); r.compute_until(10)
    assert r.save_committed(store,"world",4.7)==4.
    reloaded=ParkRuntime([domain()])
    assert reloaded.load_committed(store,"world")
    assert reloaded.time_s==4.
    reloaded.compute_until(10)
    assert reloaded.domains["river"].snapshot()==r.domains["river"].snapshot()
    store.close()

def test_persistence_checksum_and_model_guard(tmp_path):
    store=StateStore(tmp_path/"state.db")
    store.save("world","model1",0,0,{"ok":True})
    with pytest.raises(ValueError): store.load("world","model2")
    store.db.execute("UPDATE checkpoints SET sha256='bad'")
    with pytest.raises(ValueError): store.load("world","model1")
    store.close()

def test_store_transaction_rolls_back(tmp_path):
    store=StateStore(tmp_path/"state.db")
    event={"event_id":"one","at_s":0.,"revision":1,"value":1}
    store.save("world","model",0,1,{"value":1},[event])
    with pytest.raises(ValueError):
        store.save("world","model",1,2,{"value":2},[{**event,"value":2}])
    assert store.load("world","model")["checkpoint"]=={"value":1}
    store.close()

def test_history_is_bounded():
    r=ParkRuntime([domain()],history_s=4,max_frames=32)
    for i in range(1,100):
        r.advance_one(float(i)); r.prune(max(0,i-3))
    assert len(r._frames)<12

def test_shared_forcing_and_interval_means():
    timeline=ForcingTimeline(1000,[{"t_s":0.,"rain_mm_h":0.,"air_c":10.},
        {"t_s":10.,"rain_mm_h":20.,"air_c":12.},{"t_s":20.,"rain_mm_h":0.,"air_c":10.}])
    assert timeline.at(5)["epoch_unix"]==1005
    assert timeline.interval_mean(0,20,"rain_mm_h")==10.
    with pytest.raises(ValueError): timeline.at(21)
    step=ForcingTimeline(0,[{"t_s":0.,"rain":0.},{"t_s":10.,"rain":20.},{"t_s":20.,"rain":0.}],mode="previous")
    assert step.interval_mean(0,20,"rain")==10.


def test_timeline_admission_does_not_partially_advance():
    r=ParkRuntime([domain()],max_frames=3)
    r.compute_until(2)
    old=r.domains["river"].snapshot()
    with pytest.raises(RuntimeError): r.advance_one(3)
    assert r.time_s==2 and r.domains["river"].snapshot()==old
