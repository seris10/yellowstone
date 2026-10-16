"""Prescribed forcing timeline shared by the spatial domains.

Times are UTC; spatial offsets are explicit model parameters."""
from __future__ import annotations
from bisect import bisect_right
import copy
from .contracts import finite

class ForcingTimeline:
    def __init__(self, epoch_unix: float, samples: list[dict], *, mode="linear"):
        self.epoch_unix = finite(epoch_unix,"epoch_unix")
        if mode not in {"linear","previous"} or not samples:
            raise ValueError("a nonempty linear or previous-value timeline is required")
        self.mode = mode
        self.samples = copy.deepcopy(samples)
        self.times = [finite(s["t_s"],"t_s") for s in samples]
        if self.times[0] != 0. or any(b<=a for a,b in zip(self.times,self.times[1:])):
            raise ValueError("forcing must start at zero and increase strictly")
        keys=set(samples[0])-{"t_s"}
        if not keys:
            raise ValueError("forcing contains no fields")
        for sample in samples:
            if set(sample)-{"t_s"} != keys:
                raise ValueError("forcing field sets must agree")
            for key in keys:
                finite(sample[key],key)
        self.fields=tuple(sorted(keys))

    def at(self,time_s: float) -> dict:
        time_s=finite(time_s,"time_s")
        if not self.times[0]<=time_s<=self.times[-1]:
            raise ValueError("forcing outside declared temporal coverage; no silent extrapolation")
        index=max(0,bisect_right(self.times,time_s)-1)
        a=self.samples[index]
        b=self.samples[min(index+1,len(self.samples)-1)]
        span=b["t_s"]-a["t_s"]
        w=(time_s-a["t_s"])/span if span and self.mode=="linear" else 0.
        return {"t_s":time_s,"epoch_unix":self.epoch_unix+time_s,
                **{key:float(a[key])+(float(b[key])-float(a[key]))*w for key in self.fields}}

    def interval_mean(self,start_s: float,end_s: float,field: str) -> float:
        """Return the time-weighted mean of a field across breakpoints."""
        if end_s<=start_s or field not in self.fields:
            raise ValueError("invalid interval or field")
        self.at(start_s)
        self.at(end_s)
        points=[start_s]+[t for t in self.times if start_s<t<end_s]+[end_s]
        integral=0.
        for a,b in zip(points,points[1:]):
            value=self.at(a)[field]
            if self.mode=="linear":
                value=(value+self.at(b)[field])*0.5
            integral+=(b-a)*value
        return integral/(end_s-start_s)
