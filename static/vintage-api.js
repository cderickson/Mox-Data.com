  document.addEventListener('DOMContentLoaded', function() {
    const endpointCards = document.querySelectorAll('.api-endpoints-card .section-card-body');

    endpointCards.forEach((body) => {
      const nodes = Array.from(body.children);
      if (!nodes.some((node) => node.tagName === 'H3')) {
        return;
      }

      body.innerHTML = '';
      let currentDetails = null;
      let currentContent = null;

      nodes.forEach((node) => {
        if (node.tagName === 'H3') {
          currentDetails = document.createElement('details');
          currentDetails.className = 'api-endpoint-item';

          const summary = document.createElement('summary');
          summary.textContent = node.textContent.trim();
          currentDetails.appendChild(summary);

          currentContent = document.createElement('div');
          currentContent.className = 'api-endpoint-content';
          currentDetails.appendChild(currentContent);

          body.appendChild(currentDetails);
        } else if (currentContent) {
          currentContent.appendChild(node);
        } else {
          body.appendChild(node);
        }
      });
    });
  });