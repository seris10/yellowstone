export function gridIndex(grid,x,z){const [ox,oz]=grid.origin_xz_m,c=Math.floor((x-ox)/grid.cell_size_m),r=Math.floor((z-oz)/grid.cell_size_m);return c<0||r<0||c>=grid.nx||r>=grid.nz?null:r*grid.nx+c;}
export function gridSample(values,grid,x,z){const i=gridIndex(grid,x,z);return i===null||!Number.isFinite(values[i])||values[i]<0?null:values[i];}
export function transect(values,grid,a,b){const length=Math.hypot(b[0]-a[0],b[1]-a[1]),steps=Math.max(1,Math.ceil(length/grid.cell_size_m));return Array.from({length:steps+1},(_,i)=>{const t=i/steps,x=a[0]+(b[0]-a[0])*t,z=a[1]+(b[1]-a[1])*t;return {distance_m:t*length,x,z,value:gridSample(values,grid,x,z)};});}
export function weatherAt(rows,time){let i=0;while(i+1<rows.length&&rows[i+1].t_s<=time)i++;return rows[i];}
