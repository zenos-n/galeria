"""Justified rows shared by the native widget and its geometry checks."""
from bisect import bisect_left,bisect_right


class RowLayout:
    """Index whole rows; create per-photo rectangles only for the requested band."""
    def __init__(self,ratios,width,target=154,gap=3):
        self.ratios=[max(.05,float(ratio)) for ratio in ratios]
        self.width=width;self.gap=gap;self.rows=[];self.ys=[];self.height=0;self.max_height=0
        if not self.ratios or width<=0:return
        start=0;total=0.;y=0
        for index,ratio in enumerate(self.ratios):
            total+=ratio
            count=index-start+1
            if total*target+gap*(count-1)>=width:
                height=max(1,round((width-gap*(count-1))/total))
                self.rows.append((start,index+1,y,height));self.ys.append(y)
                self.max_height=max(self.max_height,height)
                y+=height+gap;start=index+1;total=0.
        if start<len(self.ratios):
            height=max(1,round(min(target,(width-gap*(len(self.ratios)-start-1))/total)))
            self.rows.append((start,len(self.ratios),y,height));self.ys.append(y)
            self.max_height=max(self.max_height,height);y+=height+gap
        self.height=y-gap

    def visible(self,low,high):
        a=bisect_left(self.ys,low-self.max_height);b=bisect_right(self.ys,high)
        for start,end,y,height in self.rows[a:b]:
            if y+height<low:continue
            x=0
            for index in range(start,end):
                width=min(max(1,round(height*self.ratios[index])),max(1,self.width-x))
                yield index,x,y,width,height
                x+=width+self.gap


def justified_rows(ratios, width, target=154, gap=3):
    if not ratios or width <= 0:
        return []
    rows, row, total = [], [], 0.0
    for index, ratio in enumerate(ratios):
        ratio = max(0.05, float(ratio))
        row.append((index, ratio))
        total += ratio
        if total * target + gap * (len(row) - 1) >= width:
            rows.append((row, (width - gap * (len(row) - 1)) / total))
            row, total = [], 0.0
    if row:
        rows.append((row, min(target, (width - gap * (len(row) - 1)) / total)))
    result, y = [], 0
    for row, height in rows:
        height = max(1, round(height))
        x = 0
        for index, ratio in row:
            item_width = max(1, round(height * ratio))
            item_width = min(item_width, max(1, width - x))
            result.append((index, x, y, item_width, height))
            x += item_width + gap
        y += height + gap
    return result
