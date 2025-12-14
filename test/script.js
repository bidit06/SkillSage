/* ================================================
   SKILLSAGE - INTERACTIVE JAVASCRIPT
   Premium interactions and animations
   ================================================ */

// === MOBILE MENU TOGGLE === 
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const mobileMenu = document.getElementById('mobile-menu');

if (mobileMenuBtn) {
    mobileMenuBtn.addEventListener('click', () => {
        mobileMenu.classList.toggle('hidden');
    });
}

// Close mobile menu when clicking on a link
const mobileLinks = mobileMenu?.querySelectorAll('a');
mobileLinks?.forEach(link => {
    link.addEventListener('click', () => {
        mobileMenu.classList.add('hidden');
    });
});

// === SMOOTH SCROLL ===
document.querySelectorAll('a[href^="#"]').forEach(anchor => {
    anchor.addEventListener('click', function (e) {
        e.preventDefault();
        const target = document.querySelector(this.getAttribute('href'));
        if (target) {
            target.scrollIntoView({
                behavior: 'smooth',
                block: 'start'
            });
        }
    });
});

// === SCROLL ANIMATIONS ===
const observerOptions = {
    threshold: 0.1,
    rootMargin: '0px 0px -100px 0px'
};

const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            entry.target.classList.add('animate-fade-in-up');
            observer.unobserve(entry.target);
        }
    });
}, observerOptions);

// Observe all sections
document.querySelectorAll('section').forEach(section => {
    observer.observe(section);
});

// === DEMO CHAT FUNCTIONALITY ===
const chatMessages = document.getElementById('chat-messages');
const chatInput = document.getElementById('demo-chat-input');

// Demo responses from Orion
const demoResponses = {
    "data science": "Great choice! To become a Data Scientist, you'll need: Python, Machine Learning, Statistics, SQL, and Data Visualization. The average learning time is 6-8 months. Would you like to see a detailed roadmap? 📊",
    "full stack": "Awesome! For Full Stack Development, focus on: JavaScript, React, Node.js, MongoDB, HTML/CSS. Estimated time: 4-6 months. I can show you our complete roadmap with projects! 💻",
    "python": "Python is a fantastic choice! For beginners, it takes about 2-3 months to learn basics, and 4-6 months to become job-ready. I recommend starting with variables, loops, functions, then moving to libraries like Pandas and NumPy. 🐍",
    "skills": "I can help you analyze your skills gap! Just create a profile and I'll compare your current skills with your target career's requirements. You'll get a personalized report with priorities and learning times. 📈",
    "salary": "Salaries vary by role and location. For example, Data Scientists in India earn ₹6-25 LPA, Full Stack Developers earn ₹4-20 LPA, and Product Managers earn ₹8-30 LPA. Want details for a specific role? 💰",
    "roadmap": "I have detailed roadmaps for Data Science, Full Stack Development, and DevOps! Each includes weekly milestones, project recommendations, and estimated completion times. Which one interests you? 🗺️",
    "default": "That's a great question! I'm trained on 105 careers and 110 skills. Try asking about specific careers like 'Data Scientist', 'Full Stack Developer', or ask 'What skills do I need for [career]?' I'm here to help! 🤖"
};

function sendDemoMessage() {
    const input = chatInput.value.trim().toLowerCase();
    if (!input) return;

    // Add user message
    addMessage(chatInput.value, 'user');
    chatInput.value = '';

    // Simulate typing indicator
    setTimeout(() => {
        addTypingIndicator();

        // Find matching response
        setTimeout(() => {
            removeTypingIndicator();
            let response = demoResponses.default;

            // Check for keywords
            for (const [key, value] of Object.entries(demoResponses)) {
                if (input.includes(key) && key !== 'default') {
                    response = value;
                    break;
                }
            }

            addMessage(response, 'orion');
        }, 1500);
    }, 300);
}

function addMessage(text, sender) {
    const messageDiv = document.createElement('div');
    messageDiv.className = `message message-${sender}`;

    const avatar = document.createElement('div');
    avatar.className = 'message-avatar';
    avatar.textContent = sender === 'orion' ? '🤖' : '👤';

    const content = document.createElement('div');
    content.className = 'message-content';
    content.innerHTML = `<p>${text}</p>`;

    messageDiv.appendChild(avatar);
    messageDiv.appendChild(content);
    chatMessages.appendChild(messageDiv);

    // Scroll to bottom
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function addTypingIndicator() {
    const indicator = document.createElement('div');
    indicator.className = 'message message-orion typing-indicator';
    indicator.innerHTML = `
        <div class="message-avatar">🤖</div>
        <div class="message-content">
            <p>Orion is typing<span class="typing-dots">...</span></p>
        </div>
    `;
    chatMessages.appendChild(indicator);
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

function removeTypingIndicator() {
    const indicator = chatMessages.querySelector('.typing-indicator');
    if (indicator) {
        indicator.remove();
    }
}

function handleChatKeypress(event) {
    if (event.key === 'Enter') {
        sendDemoMessage();
    }
}

function askQuestion(question) {
    chatInput.value = question;
    sendDemoMessage();
}

// === FAQ ACCORDION ===
function toggleFAQ(button) {
    const faqItem = button.parentElement;
    const isActive = faqItem.classList.contains('active');

    // Close all FAQs
    document.querySelectorAll('.faq-item').forEach(item => {
        item.classList.remove('active');
    });

    // Toggle current FAQ
    if (!isActive) {
        faqItem.classList.add('active');
    }
}

// === SCROLL TO TOP BUTTON ===
const scrollToTopBtn = document.getElementById('scroll-to-top');

window.addEventListener('scroll', () => {
    if (window.pageYOffset > 500) {
        scrollToTopBtn.classList.add('show');
    } else {
        scrollToTopBtn.classList.remove('show');
    }
});

function scrollToTop() {
    window.scrollTo({
        top: 0,
        behavior: 'smooth'
    });
}

// === NAVBAR BACKGROUND ON SCROLL ===
const navbar = document.querySelector('.nav-bar');
let lastScroll = 0;

window.addEventListener('scroll', () => {
    const currentScroll = window.pageYOffset;

    if (currentScroll > 50) {
        navbar.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.1)';
    } else {
        navbar.style.boxShadow = '0 4px 20px rgba(0, 102, 255, 0.15)';
    }

    lastScroll = currentScroll;
});

// === DEMO VIDEO PLAY ===
function playDemo() {
    // You can integrate a modal with video here
    alert('Demo video will play here! (Integrate your actual demo video)');
    // Or redirect to YouTube/Vimeo
    // window.open('YOUR_DEMO_VIDEO_URL', '_blank');
}

// === NUMBER COUNTER ANIMATION ===
function animateCounter(element, target, duration = 2000) {
    let start = 0;
    const increment = target / (duration / 16);

    const timer = setInterval(() => {
        start += increment;
        if (start >= target) {
            element.textContent = target + (element.dataset.suffix || '');
            clearInterval(timer);
        } else {
            element.textContent = Math.floor(start) + (element.dataset.suffix || '');
        }
    }, 16);
}

// Animate stats when they come into view
const statsObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const number = entry.target;
            const target = parseInt(number.textContent.replace(/[^0-9]/g, ''));
            animateCounter(number, target);
            statsObserver.unobserve(number);
        }
    });
}, { threshold: 0.5 });

document.querySelectorAll('.stat-number').forEach(stat => {
    statsObserver.observe(stat);
});

// === PROGRESS BAR ANIMATION ===
const progressObserver = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
        if (entry.isIntersecting) {
            const fills = entry.target.querySelectorAll('.progress-bar-fill');
            fills.forEach(fill => {
                const width = fill.style.width;
                fill.style.width = '0';
                setTimeout(() => {
                    fill.style.width = width;
                }, 100);
            });
            progressObserver.unobserve(entry.target);
        }
    });
}, { threshold: 0.3 });

document.querySelectorAll('.progress-bar-bg').forEach(bar => {
    progressObserver.observe(bar.parentElement);
});

// === TYPING EFFECT FOR HERO ===
function typeWriter(element, text, speed = 50) {
    let i = 0;
    element.textContent = '';

    function type() {
        if (i < text.length) {
            element.textContent += text.charAt(i);
            i++;
            setTimeout(type, speed);
        }
    }

    type();
}

// Optional: Add typing effect to hero subtitle
// Uncomment if you want this effect
/*
window.addEventListener('load', () => {
    const subtitle = document.querySelector('.hero-subtitle');
    if (subtitle) {
        const text = subtitle.textContent;
        typeWriter(subtitle, text, 30);
    }
});
*/

// === PARTICLE EFFECT (Optional) ===
// Uncomment to add floating particles to hero section
/*
function createParticles() {
    const hero = document.querySelector('.hero-section');
    const particlesContainer = document.createElement('div');
    particlesContainer.className = 'particles';
    particlesContainer.style.cssText = 'position: absolute; inset: 0; pointer-events: none;';

    for (let i = 0; i < 50; i++) {
        const particle = document.createElement('div');
        particle.style.cssText = `
            position: absolute;
            width: 4px;
            height: 4px;
            background: white;
            border-radius: 50%;
            left: ${Math.random() * 100}%;
            top: ${Math.random() * 100}%;
            opacity: ${Math.random() * 0.5};
            animation: float ${5 + Math.random() * 10}s infinite ease-in-out;
        `;
        particlesContainer.appendChild(particle);
    }

    hero.appendChild(particlesContainer);
}

window.addEventListener('load', createParticles);
*/

// === EASTER EGG: Konami Code ===
let konamiCode = [];
const konamiSequence = ['ArrowUp', 'ArrowUp', 'ArrowDown', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'ArrowLeft', 'ArrowRight', 'b', 'a'];

document.addEventListener('keydown', (e) => {
    konamiCode.push(e.key);
    konamiCode = konamiCode.slice(-10);

    if (konamiCode.join('') === konamiSequence.join('')) {
        // Easter egg activated!
        document.body.style.animation = 'rainbow 2s infinite';
        setTimeout(() => {
            document.body.style.animation = '';
            alert('🎉 You found the secret! You get 10% extra career clarity! 🚀');
        }, 2000);
    }
});

// === PREFETCH LINKS (Performance Optimization) ===
document.querySelectorAll('a[href^="/"]').forEach(link => {
    link.addEventListener('mouseenter', () => {
        const href = link.getAttribute('href');
        if (href && !document.querySelector(`link[href="${href}"]`)) {
            const prefetch = document.createElement('link');
            prefetch.rel = 'prefetch';
            prefetch.href = href;
            document.head.appendChild(prefetch);
        }
    });
});

// === LOADING ANIMATION ===
window.addEventListener('load', () => {
    // Hide loader if you have one
    const loader = document.getElementById('loader');
    if (loader) {
        loader.style.opacity = '0';
        setTimeout(() => loader.style.display = 'none', 300);
    }

    // Trigger initial animations
    console.log('🚀 SkillsAge loaded successfully!');
});

// === ANALYTICS TRACKING (Placeholder) ===
function trackEvent(category, action, label) {
    // Integrate with Google Analytics or your preferred analytics
    console.log('Event tracked:', { category, action, label });

    // Example: Google Analytics 4
    // gtag('event', action, {
    //     'event_category': category,
    //     'event_label': label
    // });
}

// Track CTA clicks
document.querySelectorAll('.btn-primary, .btn-hero-primary').forEach(btn => {
    btn.addEventListener('click', () => {
        trackEvent('CTA', 'Click', 'Get Started Free');
    });
});

// Track feature card clicks
document.querySelectorAll('.feature-link').forEach(link => {
    link.addEventListener('click', () => {
        trackEvent('Features', 'Click', link.textContent.trim());
    });
});

// === CONSOLE MESSAGE ===
console.log('%c🚀 SkillsAge - Your AI Career Companion', 'color: #0066FF; font-size: 20px; font-weight: bold;');
console.log('%c💼 Developed with ❤️ for your career success', 'color: #6B7280; font-size: 14px;');
console.log('%c🔧 Looking for a job? Visit /dashboard to get started!', 'color: #00C853; font-size: 14px;');

// === AUTO-SAVE FORM (If you add contact form) ===
function autoSaveForm(formId) {
    const form = document.getElementById(formId);
    if (!form) return;

    const inputs = form.querySelectorAll('input, textarea, select');

    inputs.forEach(input => {
        // Load saved value
        const savedValue = localStorage.getItem(`${formId}_${input.name}`);
        if (savedValue) input.value = savedValue;

        // Save on change
        input.addEventListener('input', () => {
            localStorage.setItem(`${formId}_${input.name}`, input.value);
        });
    });

    // Clear on submit
    form.addEventListener('submit', () => {
        inputs.forEach(input => {
            localStorage.removeItem(`${formId}_${input.name}`);
        });
    });
}

// === THEME TOGGLE (Optional Dark Mode) ===
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

// Load saved theme
const savedTheme = localStorage.getItem('theme');
if (savedTheme) {
    document.documentElement.setAttribute('data-theme', savedTheme);
}

// === VIEWPORT HEIGHT FIX (Mobile) ===
function setViewportHeight() {
    let vh = window.innerHeight * 0.01;
    document.documentElement.style.setProperty('--vh', `${vh}px`);
}

setViewportHeight();
window.addEventListener('resize', setViewportHeight);

// === LAZY LOAD IMAGES ===
if ('loading' in HTMLImageElement.prototype) {
    // Native lazy loading supported
    const images = document.querySelectorAll('img[loading="lazy"]');
    images.forEach(img => {
        img.src = img.dataset.src;
    });
} else {
    // Fallback for browsers that don't support lazy loading
    const images = document.querySelectorAll('img[data-src]');
    const imageObserver = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            if (entry.isIntersecting) {
                const img = entry.target;
                img.src = img.dataset.src;
                img.classList.add('loaded');
                imageObserver.unobserve(img);
            }
        });
    });

    images.forEach(img => imageObserver.observe(img));
}

console.log('✅ All interactive features loaded!');