export interface MapLayout {
    leftWidth: string;
    rightHidden: boolean;
    dividerHidden: boolean;
}

export function mapLayout(enabled: boolean, savedPosition: string): MapLayout {
    if (!enabled) return { leftWidth: '100%', rightHidden: true, dividerHidden: true };
    const percentage = Number.parseFloat(savedPosition);
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
    const maximumWidth = Math.max(minimumWidth, parentWidth - minimumWidth - dividerWidth);
    return Math.min(maximumWidth, Math.max(minimumWidth, startWidth + delta));
}

export function recordingDividerPct(enabled: boolean, containerWidth: number, leftWidth: number): number {
    if (!enabled || containerWidth <= 0) return 50;
    return Number(((leftWidth / containerWidth) * 100).toFixed(2));
}
