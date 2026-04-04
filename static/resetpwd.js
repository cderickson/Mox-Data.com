document.addEventListener('DOMContentLoaded', function() {
  const passwordToggles = document.querySelectorAll('.password-toggle');
  passwordToggles.forEach(toggle => {
    toggle.addEventListener('click', function() {
      const input = this.previousElementSibling;
      const type = input.type === 'password' ? 'text' : 'password';
      input.type = type;

      const icon = this.querySelector('i');
      if (icon) {
        icon.className = type === 'password' ? 'fas fa-eye' : 'fas fa-eye-slash';
      }
    });
  });

  const passwordInput = document.getElementById('new_pwd');
  const confirmInput = document.getElementById('new_pwd_confirm');
  const matchIndicator = document.getElementById('password-match-indicator');

  function checkPasswordMatch() {
    if (!confirmInput.value) {
      matchIndicator.textContent = '';
      return;
    }

    if (passwordInput.value === confirmInput.value) {
      matchIndicator.textContent = '✓ Passwords match';
      matchIndicator.style.color = '#22c55e';
    } else {
      matchIndicator.textContent = '✗ Passwords do not match';
      matchIndicator.style.color = 'red';
    }
  }

  if (confirmInput && matchIndicator) {
    confirmInput.addEventListener('input', checkPasswordMatch);
    passwordInput.addEventListener('input', checkPasswordMatch);
  }

  const form = document.querySelector('form');
  if (form) {
    form.addEventListener('submit', function(e) {
      const password = passwordInput.value;
      const confirmPassword = confirmInput.value;

      if (!password || !confirmPassword) {
        e.preventDefault();
        alert('Please fill in both password fields.');
        return;
      }

      if (password !== confirmPassword) {
        e.preventDefault();
        alert('Passwords do not match.');
        return;
      }

      if (password.length < 6) {
        e.preventDefault();
        alert('Password must be at least 6 characters long.');
        return;
      }

      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.innerHTML = '<span class="spinner"></span> Updating Password...';
      submitBtn.disabled = true;
    });
  }

  const firstInput = document.getElementById('new_pwd');
  if (firstInput) {
    firstInput.focus();
  }
});