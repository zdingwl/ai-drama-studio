export function personImageViewport(size: [number, number] | null, box?: number[] | null): string | null {
  if (!size || !box || box.length !== 4) return null
  const [x,y,w,h] = box as [number,number,number,number]
  const [width,height] = size
  if (![x,y,w,h,width,height].every(Number.isFinite) || x < 0 || y < 0 || w <= 0 || h <= 0 || width <= 0 || height <= 0 || x+w > 1.000001 || y+h > 1.000001) return null
  return `${x*width} ${y*height} ${w*width} ${h*height}`
}
