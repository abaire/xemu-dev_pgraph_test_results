function enableImagePairs(document) {
    const imagePairs = document.querySelectorAll('.image-group');

    imagePairs.forEach(pair => {
        const images = pair.querySelectorAll('.image-comparison');
        const titles = pair.querySelectorAll('.image-title');
        let activeState = 'source';

        function applyActiveState(newState) {
            images.forEach(img => {
                img.style.display = (img.dataset.state === newState) ? 'block' : 'none';
            });

            titles.forEach(title => {
                title.style.fontWeight = (title.dataset.state === newState) ? 'bold' : 'normal';
            });

            pair.classList.remove("image-group-golden");
            pair.classList.remove("image-group-golden-xemu");

            if (newState === 'golden-xemu') {
                pair.classList.add("image-group-golden-xemu");
            } else if (newState === 'golden-hw') {
                pair.classList.add("image-group-golden");
            }

            activeState = newState;
        }

        function swapImagesAndTitles() {
            var newState;
            switch (activeState) {
                case "source":
                    newState = "golden-xemu";
                    break;
                case "golden-xemu":
                    newState = "golden-hw";
                    break;
                default:
                    newState = "source";
                    break;
            }
            applyActiveState(newState);
        }

        applyActiveState(activeState);
        images.forEach(img => {
            img.addEventListener('click', swapImagesAndTitles);
        });
    });
}

function enableViewLinks(document) {
    const viewLinks = document.querySelectorAll('.view-link');

    viewLinks.forEach(link => {

        const container = link.closest('.titled-image-container');
        if (container) {
            const hiddenImage = container.querySelector('.hidden-image');
            if (hiddenImage) {

                link.addEventListener('click', (event) => {
                    event.preventDefault();
                    hiddenImage.style.display = 'block';
                    link.style.display = 'none';
                });

                hiddenImage.addEventListener('click', () => {
                    hiddenImage.style.display = 'none';
                    link.style.display = 'block';
                });
            }
        }
    });
}

function enableAnchorCopying(document) {
    function addClickHandler(element) {
        if (element.id) {
            element.style.cursor = 'pointer';
            element.addEventListener('click', () => {
                const currentURL = window.location.href.split('.html')[0];
                const anchor = element.id;
                const urlWithAnchor = `${currentURL}.html#${anchor}`;

                navigator.clipboard.writeText(urlWithAnchor)
            });
        }
    }

    const h2Elements = document.querySelectorAll('h2');
    h2Elements.forEach(addClickHandler);
    const h3Elements = document.querySelectorAll('h3');
    h3Elements.forEach(addClickHandler);
    const h4Elements = document.querySelectorAll('h4');
    h4Elements.forEach(addClickHandler);
}

document.addEventListener('DOMContentLoaded', () => {
    enableViewLinks(document);
    enableImagePairs(document);
    enableAnchorCopying(document);
});