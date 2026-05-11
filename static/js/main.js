const form = document.getElementById('inquiryForm');
const loader = document.getElementById('loader');
const modal = document.getElementById('successModal');
const closeModal = document.getElementById('closeModal');

document.querySelectorAll('.reveal').forEach(el => {
  const observer = new IntersectionObserver(([entry]) => {
    if (entry.isIntersecting) el.classList.add('visible');
  }, { threshold: 0.12 });
  observer.observe(el);
});

if (form) {
  form.addEventListener('submit', () => {
    loader.classList.remove('hidden');
    const btn = document.getElementById('submitBtn');
    btn.disabled = true;
    btn.textContent = 'Sending...';
  });
}

if (document.querySelector('.alert.success') && modal) {
  modal.classList.remove('hidden');
}

if (closeModal && modal) {
  closeModal.addEventListener('click', () => modal.classList.add('hidden'));
}