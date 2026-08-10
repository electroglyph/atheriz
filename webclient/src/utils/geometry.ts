import { Point } from '../types';

/**
 * Bresenham's line algorithm to get all points between p0 and p1
 */
export function getLinePoints(p0: Point, p1: Point): Point[] {
    const points: Point[] = [];
    let x0 = Math.floor(p0.x);
    let y0 = Math.floor(p0.y);
    const x1 = Math.floor(p1.x);
    const y1 = Math.floor(p1.y);

    const dx = Math.abs(x1 - x0);
    const dy = Math.abs(y1 - y0);
    const sx = x0 < x1 ? 1 : -1;
    const sy = y0 < y1 ? 1 : -1;
    let err = dx - dy;

    while (true) {
        points.push({ x: x0, y: y0 });
        if (x0 === x1 && y0 === y1) break;
        const e2 = 2 * err;
        if (e2 > -dy) {
            err -= dy;
            x0 += sx;
        }
        if (e2 < dx) {
            err += dx;
            y0 += sy;
        }
    }
    return points;
}

/**
 * Midpoint ellipse algorithm to get perimeter points
 */
export function getEllipsePerimeter(x0: number, y0: number, x1: number, y1: number, make4Connected: boolean = false): Point[] {
    const points: Point[] = [];
    
    const a = Math.abs(x1 - x0) / 2;
    const b = Math.abs(y1 - y0) / 2;
    const cx = Math.min(x0, x1) + a;
    const cy = Math.min(y0, y1) + b;
    
    if (a === 0 && b === 0) {
        return [{ x: Math.round(x0), y: Math.round(y0) }];
    }
    
    if (a === 0) {
        return getLinePoints({x: x0, y: Math.min(y0, y1)}, {x: x0, y: Math.max(y0, y1)});
    }
    
    if (b === 0) {
        return getLinePoints({x: Math.min(x0, x1), y: y0}, {x: Math.max(x0, x1), y: y0});
    }

    let x = 0;
    let y = b;
    let d1 = (b * b) - (a * a * b) + (0.25 * a * a);
    let dx = 2 * b * b * x;
    let dy = 2 * a * a * y;

    const addSymmetricPoints = (px: number, py: number) => {
        points.push({ x: Math.round(cx + px), y: Math.round(cy + py) });
        points.push({ x: Math.round(cx - px), y: Math.round(cy + py) });
        points.push({ x: Math.round(cx + px), y: Math.round(cy - py) });
        points.push({ x: Math.round(cx - px), y: Math.round(cy - py) });
    };

    while (dx < dy) {
        addSymmetricPoints(x, y);
        if (d1 < 0) {
            x++;
            dx += (2 * b * b);
            d1 += dx + (b * b);
        } else {
            x++;
            y--;
            if (make4Connected) {
                addSymmetricPoints(x, y + 1);
            }
            dx += (2 * b * b);
            dy -= (2 * a * a);
            d1 += dx - dy + (b * b);
        }
    }

    let d2 = ((b * b) * ((x + 0.5) * (x + 0.5))) + ((a * a) * ((y - 1) * (y - 1))) - (a * a * b * b);

    while (y >= 0) {
        addSymmetricPoints(x, y);
        if (d2 > 0) {
            y--;
            dy -= (2 * a * a);
            d2 += (a * a) - dy;
        } else {
            y--;
            x++;
            if (make4Connected) {
                addSymmetricPoints(x - 1, y);
            }
            dx += (2 * b * b);
            dy -= (2 * a * a);
            d2 += dx - dy + (a * a);
        }
    }

    // Deduplicate
    const unique = new Map<string, Point>();
    for (const p of points) {
        unique.set(`${p.x},${p.y}`, p);
    }
    return Array.from(unique.values());
}
