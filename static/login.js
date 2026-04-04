// Redis.io Inspired Login JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const loginForm = document.getElementById('loginForm');

    // Form submission handling
    if (loginForm) {
        loginForm.addEventListener('submit', function(e) {
            // Allow normal form submission to backend
            // Remove preventDefault to let Flask handle the form
        });
    }

    // Password visibility toggle functionality
    const passwordToggles = document.querySelectorAll('.password-toggle');
    passwordToggles.forEach(toggle => {
        toggle.addEventListener('click', function() {
            const input = this.parentElement.querySelector('input');
            const icon = this.querySelector('i');
            
            if (input.type === 'password') {
                input.type = 'text';
                icon.className = 'fas fa-eye-slash';
            } else {
                input.type = 'password';
                icon.className = 'fas fa-eye';
            }
        });
    });

    // Enhanced form validation and UX
    const emailInput = document.getElementById('login_email');
    const passwordInput = document.getElementById('login_pwd');

    if (emailInput) {
        emailInput.addEventListener('blur', function() {
            validateEmail(this);
        });
    }

    if (passwordInput) {
        passwordInput.addEventListener('input', function() {
            clearFieldError(this);
        });
    }

    function validateEmail(input) {
        const email = input.value.trim();
        const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
        
        if (email && !emailRegex.test(email)) {
            showFieldError(passwordInput, 'Please enter a valid email address');
            return false;
        } else {
            clearFieldError(input);
            return true;
        }
    }

    function showFieldError(input, message) {
        clearFieldError(input);
        
        const errorDiv = document.createElement('div');
        errorDiv.className = 'field-error';
        errorDiv.style.cssText = `
            color: var(--redis-red);
            font-size: 0.875rem;
            margin-top: 0.5rem;
            padding: 0.25rem 0;
            display: block;
            width: 100%;
        `;
        errorDiv.textContent = message;
        
        // Find the form-group container to append error after it
        let container = input.parentElement;
        if (container.tagName === 'DIV' && !container.classList.contains('form-group')) {
            container = container.parentElement; // Go up one more level if needed
        }
        container.appendChild(errorDiv);
        input.style.borderColor = 'var(--redis-red)';
    }

    function clearFieldError(input) {
        // Find the form-group container to look for errors
        let container = input.parentElement;
        if (container.tagName === 'DIV' && !container.classList.contains('form-group')) {
            container = container.parentElement; // Go up one more level if needed
        }
        const existingError = container.querySelector('.field-error');
        if (existingError) {
            existingError.remove();
        }
        input.style.borderColor = '';
    }

    // Show alert messages
    function showAlert(message, type) {
        // Create alert element
        const alert = document.createElement('div');
        alert.className = `alert ${type}`;
        alert.style.cssText = `
            position: fixed;
            top: 20px;
            right: 20px;
            max-width: 400px;
            z-index: 9999;
            padding: 1rem;
            border-radius: var(--radius-sm);
            box-shadow: var(--shadow-lg);
            animation: slideIn 0.3s ease-out;
        `;
        alert.textContent = message;

        // Add to page
        document.body.appendChild(alert);

        // Auto remove after 5 seconds
        setTimeout(() => {
            alert.style.animation = 'slideOut 0.3s ease-out forwards';
            setTimeout(() => {
                if (alert.parentElement) {
                    alert.parentElement.removeChild(alert);
                }
            }, 300);
        }, 5000);
    }

    // Keyboard navigation improvements
    document.addEventListener('keydown', function(e) {
        // Enter key on email field focuses password field
        if (e.key === 'Enter' && e.target === emailInput && passwordInput) {
            e.preventDefault();
            passwordInput.focus();
        }
    });

    // Focus management for better UX
    if (emailInput && !emailInput.value) {
        emailInput.focus();
    }

    const resetModal = document.getElementById('resetModal');
    if (resetModal) {
        resetModal.addEventListener('click', function(e) {
            if (e.target === this) {
                hideResetModal();
            }
        });
    }
});

// CSS animations for alerts
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }

    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }

    .field-error {
        animation: fadeIn 0.3s ease-out;
    }

    @keyframes fadeIn {
        from {
            opacity: 0;
            transform: translateY(-10px);
        }
        to {
            opacity: 1;
            transform: translateY(0);
        }
    }
`;
document.head.appendChild(style);

// Functions for login page functionality
function showResetModal() {
    const resetModal = document.getElementById('resetModal');
    const resetEmailInput = document.getElementById('reset_email_input');
    const loginEmail = document.getElementById('login_email');
    if (resetModal) {
        resetModal.style.display = 'block';
    }
    if (resetEmailInput && loginEmail) {
        resetEmailInput.value = loginEmail.value || '';
    }
}

function hideResetModal() {
    const resetModal = document.getElementById('resetModal');
    if (resetModal) {
        resetModal.style.display = 'none';
    }
}

function sendResetEmail() {
    const emailInput = document.getElementById('reset_email_input');
    const hiddenResetEmail = document.getElementById('reset_email');
    const resetForm = document.getElementById('reset_form');
    const email = emailInput ? emailInput.value : '';
    if (!email) {
        alert('Please enter an email address');
        return;
    }

    if (hiddenResetEmail) {
        hiddenResetEmail.value = email;
    }
    if (resetForm) {
        resetForm.submit();
    }
}

function sendConfirmationEmail() {
    const loginEmail = document.getElementById('login_email');
    const confirmEmail = document.getElementById('confirm_email');
    const confirmPwd = document.getElementById('confirm_pwd');
    const confirmForm = document.getElementById('confirm_email_form');
    const email = loginEmail ? loginEmail.value : '';

    if (!email) {
        alert('Please enter your email address');
        return;
    }

    if (confirmEmail) {
        confirmEmail.value = email;
    }
    if (confirmPwd) {
        confirmPwd.value = '';
    }
    if (confirmForm) {
        confirmForm.submit();
    }
}