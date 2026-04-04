document.addEventListener('DOMContentLoaded', function() {
  const passwordInput = document.getElementById('reg_pwd');

  // Password visibility toggle
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

  // Password confirmation matching
  const confirmInput = document.getElementById('reg_pwd_confirm');
  const matchIndicator = document.getElementById('password-match-indicator');
  const form = document.querySelector('form');
  const emailInput = document.getElementById('reg_email');
  const emailIndicator = document.getElementById('reg-email-indicator');
  const usernameInput = document.getElementById('reg_hero');
  const usernameIndicator = document.getElementById('reg-username-indicator');
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  const helperColor = '#6b7280';

  function setIndicator(el, text, color) {
    if (!el) return;
    el.textContent = text;
    el.style.color = color;
  }

  function checkPasswordMatch() {
    const password = (passwordInput.value || '');
    const confirmPassword = (confirmInput.value || '');

    if (!password && !confirmPassword) {
      setIndicator(matchIndicator, 'Use at least 6 characters.', helperColor);
      return;
    }

    if (password.length < 6) {
      setIndicator(matchIndicator, '✗ Password must be at least 6 chars', '#b91c1c');
      return;
    }

    if (!confirmPassword) {
      setIndicator(matchIndicator, 'Confirm your password to validate.', helperColor);
      return;
    }

    if (password === confirmPassword) {
      setIndicator(matchIndicator, '✓ Passwords match', '#15803d');
    } else {
      setIndicator(matchIndicator, '✗ Passwords do not match', '#b91c1c');
    }
  }

  if (confirmInput && matchIndicator) {
    confirmInput.addEventListener('input', checkPasswordMatch);
    passwordInput.addEventListener('input', checkPasswordMatch);
  }

  function validateEmailField(showInvalidIndicator = false) {
    if (!emailInput || !emailIndicator) return true;
    const email = (emailInput.value || '').trim();
    const isValid = !!email && emailRegex.test(email);
    if (!email) {
      setIndicator(emailIndicator, 'Use format: name@example.com', helperColor);
      return false;
    }

    if (isValid) {
      setIndicator(emailIndicator, '✓ Valid email', '#15803d');
    } else if (showInvalidIndicator) {
      setIndicator(emailIndicator, '✗ Invalid email format', '#b91c1c');
    } else {
      setIndicator(emailIndicator, 'Use format: name@example.com', helperColor);
    }
    return isValid;
  }

  if (emailInput) {
    emailInput.addEventListener('input', () => {
      if ((emailInput.value || '').trim()) {
        validateEmailField(true);
      } else {
        setIndicator(emailIndicator, 'Use format: name@example.com', helperColor);
      }
    });
    emailInput.addEventListener('blur', () => validateEmailField(true));
  }

  function validateUsernameField(showInvalidIndicator = false) {
    if (!usernameInput || !usernameIndicator) return true;
    const username = (usernameInput.value || '').trim();
    const isValid = username.length >= 3 && username.length <= 20;

    if (!username) {
      setIndicator(usernameIndicator, 'This helps us identify your game logs.', helperColor);
      return false;
    }

    if (isValid) {
      setIndicator(usernameIndicator, '✓ Valid username', '#15803d');
    } else if (showInvalidIndicator) {
      setIndicator(usernameIndicator, '✗ Username must be 3-20 chars', '#b91c1c');
    } else {
      setIndicator(usernameIndicator, 'This helps us identify your game logs.', helperColor);
    }
    return isValid;
  }

  if (usernameInput) {
    usernameInput.addEventListener('input', () => {
      if ((usernameInput.value || '').trim()) {
        validateUsernameField(true);
      } else {
        setIndicator(usernameIndicator, 'This helps us identify your game logs.', helperColor);
      }
    });
    usernameInput.addEventListener('blur', () => validateUsernameField(true));
  }

  if (form) {
    form.addEventListener('submit', function(e) {
      const email = document.getElementById('reg_email').value;
      const password = passwordInput.value;
      const confirmPassword = confirmInput.value;
      const username = document.getElementById('reg_hero').value;
      const normalizedUsername = (username || '').trim();

      if ((email || '').trim() && !validateEmailField(true)) {
        e.preventDefault();
        return;
      }

      if (!email || !password || !confirmPassword || !normalizedUsername) {
        e.preventDefault();
        alert('Please fill in all fields.');
        return;
      }

      if (!validateUsernameField(true)) {
        e.preventDefault();
        return;
      }

      if (password.length < 6) {
        e.preventDefault();
        checkPasswordMatch();
        confirmInput.focus();
        return;
      }

      if (password !== confirmPassword) {
        e.preventDefault();
        checkPasswordMatch();
        confirmInput.focus();
        return;
      }

      const submitBtn = form.querySelector('button[type="submit"]');
      submitBtn.innerHTML = '<span class="spinner"></span> Creating Account...';
      submitBtn.disabled = true;
    });
  }

  const firstInput = document.getElementById('reg_email');
  if (firstInput) {
    firstInput.focus();
  }

  validateEmailField(false);
  validateUsernameField(false);
  checkPasswordMatch();
});