export const temperaturePalette = ['#2787eb','#24d7ca','#e3ed66','#ffb336','#ef4d69'];
export const changePalette = ['#5572ed','#62cde0','#d9dde3','#f2bb45','#ef603c'];

export function finiteRange(values) {
  let min=Infinity,max=-Infinity;
  for(const v of values)if(Number.isFinite(v)){min=Math.min(min,v);max=Math.max(max,v);}
  return min===Infinity?null:[min,max];
}
export function changeLimit(replay) {
  let max=0;
  replay.frames.forEach(f=>f.values.forEach((v,i)=>{const initial=replay.frames[0].values[i];if(Number.isFinite(v)&&Number.isFinite(initial))max=Math.max(max,Math.abs(v-initial));}));
  return Math.max(.01,Math.ceil(max*100)/100);
}
export function temperatureValue(replay,frame,index,mode) {
  const value=replay.frames[frame].values[index],initial=replay.frames[0].values[index];
  if(!Number.isFinite(value))return null;
  return mode==='change'?(Number.isFinite(initial)?value-initial:null):value;
}
export function temperatureRange(mode,globalRange,anchor,deltaLimit) {
  if(mode==='change')return [-deltaLimit,deltaLimit];
  if(mode==='focus'&&Number.isFinite(anchor))return [anchor-.05,anchor+.05];
  return [Math.floor(globalRange[0]*100)/100,Math.ceil(globalRange[1]*100)/100];
}
export function colorFraction(value,range) {
  if(!Number.isFinite(value))return null;
  return Math.max(0,Math.min(1,(value-range[0])/(range[1]-range[0])));
}
