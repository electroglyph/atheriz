export interface MapLayout {
    leftWidth: string;
    rightHidden: boolean;
    dividerHidden: boolean;
}

export function mapLayout(enabled: boolean, savedPosition: string): MapLayout {
    if (!enabled) return { leftWidth: '100%', rightHidden: true, dividerHidden: true };
    const percentage = Number.parseFloat(savedPosition.trim());
    const width = Number.isFinite(percentage) && percentage > 5 && percentage < 95 ? `${percentage}%` : '50%';
    return { leftWidth: width, rightHidden: false, dividerHidden: false };
}

export function resizeWidth(
    startWidth: number,
    parentWidth: number,
    delta: number,
    dividerWidth = 5,
    minimumWidth = 50,
): number {
    if (!Number.isFinite(startWidth) || !Number.isFinite(parentWidth) || !Number.isFinite(delta) || !Number.isFinite(dividerWidth) || !Number.isFinite(minimumWidth)) return minimumWidth;
    if (parentWidth <= 0) return minimumWidth;
    const maximumWidth = Math.max(minimumWidth, parentWidth - minimumWidth - dividerWidth);
    return Math.min(maximumWidth, Math.max(minimumWidth, startWidth + delta));
}

export function recordingDividerPct(enabled: boolean, containerWidth: number, leftWidth: number): number {
    if (!enabled || containerWidth <= 0 || !Number.isFinite(containerWidth) || !Number.isFinite(leftWidth)) return 50;
    const pct = (leftWidth / containerWidth) * 100;
    if (!Number.isFinite(pct)) return 50;
    return Number(pct.toFixed(2));
}
