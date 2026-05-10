/**
 * Crimson Studio — minimal JS
 * Scroll-triggered reveals + mobile nav toggle
 */

document.addEventListener('DOMContentLoaded', () => {

  /* === SCROLL REVEAL (Intersection Observer) === */
  const revealEls = document.querySelectorAll('[data-reveal]');
  if (revealEls.length && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          entry.target.classList.add('revealed');
          observer.unobserve(entry.target);
        }
      });
    }, {
      threshold: 0.12,
      rootMargin: '0px 0px -40px 0px'
    });

    revealEls.forEach(el => observer.observe(el));
  } else {
    /* Fallback: show all immediately */
    revealEls.forEach(el => el.classList.add('revealed'));
  }

  /* === MOBILE NAV TOGGLE === */
  const toggle = document.querySelector('.nav__toggle');
  const links = document.querySelector('.nav__links');

  if (toggle && links) {
    toggle.addEventListener('click', () => {
      const isOpen = links.classList.toggle('open');
      toggle.classList.toggle('open');
      toggle.setAttribute('aria-expanded', isOpen);
    });

    /* Close nav when a link is clicked */
    links.querySelectorAll('a').forEach(link => {
      link.addEventListener('click', () => {
        links.classList.remove('open');
        toggle.classList.remove('open');
        toggle.setAttribute('aria-expanded', 'false');
      });
    });
  }

  /* === ACTIVE NAV LINK === */
  const currentPath = window.location.pathname;
  document.querySelectorAll('.nav__links a').forEach(a => {
    const href = a.getAttribute('href');
    if (href === currentPath ||
        (href === '/' && currentPath === '/') ||
        (href !== '/' && currentPath.startsWith(href))) {
      a.classList.add('active');
    }
  });

});
