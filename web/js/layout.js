/*
 * Layout resizing helpers: network resize trigger + generic draggable resizer.
 */

export function triggerNetworkResize() {
    if (KeenStore.network) {
        try {
            KeenStore.network.setSize('100%', '100%');
            KeenStore.network.redraw();
        } catch (e) {
            console.warn('Failed to resize network visualizer', e);
        }
    }
}

export function makeResizable(resizer, resizeTarget, direction, minSize, maxSize, storageKey) {
    resizer.addEventListener('mousedown', (e) => {
        e.preventDefault();
        resizer.classList.add('dragging');
        document.body.classList.add('resizing-active');

        const startX = e.clientX;
        const startY = e.clientY;
        const startWidth = resizeTarget.offsetWidth;
        const startHeight = resizeTarget.offsetHeight;

        function onMouseMove(moveEvent) {
            if (direction === 'horizontal-left') {
                const deltaX = startX - moveEvent.clientX;
                const newWidth = Math.max(minSize, Math.min(maxSize, startWidth + deltaX));
                resizeTarget.style.width = `${newWidth}px`;
                triggerNetworkResize();
            } else if (direction === 'horizontal-right') {
                const deltaX = moveEvent.clientX - startX;
                const newWidth = Math.max(minSize, Math.min(maxSize, startWidth + deltaX));
                resizeTarget.style.width = `${newWidth}px`;
                triggerNetworkResize();
            } else if (direction === 'vertical-up') {
                const deltaY = startY - moveEvent.clientY;
                const newHeight = Math.max(minSize, Math.min(maxSize, startHeight + deltaY));
                resizeTarget.style.height = `${newHeight}px`;
            }
        }

        function onMouseUp() {
            resizer.classList.remove('dragging');
            document.body.classList.remove('resizing-active');

            if (direction.startsWith('horizontal')) {
                localStorage.setItem(storageKey, resizeTarget.offsetWidth);
                triggerNetworkResize();
            } else {
                localStorage.setItem(storageKey, resizeTarget.offsetHeight);
            }

            document.removeEventListener('mousemove', onMouseMove);
            document.removeEventListener('mouseup', onMouseUp);
        }

        document.addEventListener('mousemove', onMouseMove);
        document.addEventListener('mouseup', onMouseUp);
    });

    // Touch support
    resizer.addEventListener('touchstart', (e) => {
        if (e.touches.length !== 1) return;
        const touch = e.touches[0];
        resizer.classList.add('dragging');
        document.body.classList.add('resizing-active');

        const startX = touch.clientX;
        const startY = touch.clientY;
        const startWidth = resizeTarget.offsetWidth;
        const startHeight = resizeTarget.offsetHeight;

        function onTouchMove(moveEvent) {
            if (moveEvent.touches.length !== 1) return;
            const currentTouch = moveEvent.touches[0];
            if (direction === 'horizontal-left') {
                const deltaX = startX - currentTouch.clientX;
                const newWidth = Math.max(minSize, Math.min(maxSize, startWidth + deltaX));
                resizeTarget.style.width = `${newWidth}px`;
                triggerNetworkResize();
            } else if (direction === 'horizontal-right') {
                const deltaX = currentTouch.clientX - startX;
                const newWidth = Math.max(minSize, Math.min(maxSize, startWidth + deltaX));
                resizeTarget.style.width = `${newWidth}px`;
                triggerNetworkResize();
            } else if (direction === 'vertical-up') {
                const deltaY = startY - currentTouch.clientY;
                const newHeight = Math.max(minSize, Math.min(maxSize, startHeight + deltaY));
                resizeTarget.style.height = `${newHeight}px`;
            }
        }

        function onTouchEnd() {
            resizer.classList.remove('dragging');
            document.body.classList.remove('resizing-active');

            if (direction.startsWith('horizontal')) {
                localStorage.setItem(storageKey, resizeTarget.offsetWidth);
                triggerNetworkResize();
            } else {
                localStorage.setItem(storageKey, resizeTarget.offsetHeight);
            }

            document.removeEventListener('touchmove', onTouchMove);
            document.removeEventListener('touchend', onTouchEnd);
        }

        document.addEventListener('touchmove', onTouchMove, { passive: false });
        document.addEventListener('touchend', onTouchEnd);
    });
}
