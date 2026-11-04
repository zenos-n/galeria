"""Bounded editor snapshots; pending control changes become one undo step."""
from copy import deepcopy


class History:
    def __init__(self,state):self.past=[deepcopy(state)];self.future=[]
    def record(self,state):
        if state!=self.past[-1]:self.past.append(deepcopy(state));self.past=self.past[-50:];self.future.clear()
    def undo(self,state):
        self.record(state)
        if len(self.past)<2:return None
        self.future.append(self.past.pop());return deepcopy(self.past[-1])
    def redo(self,state):
        if state!=self.past[-1]:self.record(state);return None
        if not self.future:return None
        self.past.append(self.future.pop());return deepcopy(self.past[-1])
