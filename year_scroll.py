"""Equal space per year, proportional scrolling within each year."""


class YearScale:
    def __init__(self,months,maximum):
        self.maximum=max(0,maximum)
        years={}
        for month,(start,end) in months.items():
            year=month[:4]
            old=years.get(year,(start,end))
            years[year]=(min(start,old[0]),max(end,old[1]))
        clamp=lambda value:max(0,min(self.maximum,value))
        self.segments=[(year,clamp(start),clamp(end)) for year,(start,end) in sorted(years.items(),reverse=True)]

    def scroll(self,fraction):
        if not self.segments:return 0
        position=max(0,min(1,fraction))*len(self.segments)
        index=min(len(self.segments)-1,int(position))
        _,start,end=self.segments[index]
        return start+(end-start)*(position-index)

    def fraction(self,position):
        if not self.segments or self.maximum<=0:return 0
        if position>=self.maximum:return 1
        for index,(_,start,end) in enumerate(self.segments):
            if position<end:
                return (index+max(0,(position-start)/max(1,end-start)))/len(self.segments)
        return 1
