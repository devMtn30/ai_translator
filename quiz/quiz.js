const sidebar = document.getElementById("sidebar");
const menuBtn = document.getElementById("menuBtn");
const closeBtn = document.getElementById("closeBtn");

menuBtn.addEventListener("click", () => {
  sidebar.classList.add("open");
});

closeBtn.addEventListener("click", () => {
  sidebar.classList.remove("open");
});

// Quiz Functionality
const cebuanoBtn = document.querySelector('.quiz-btn:nth-child(1)'); // Cebuano button
const tagalogBtn = document.querySelector('.quiz-btn:nth-child(2)'); // Tagalog button
const hiligaynonBtn = document.querySelector('.quiz-btn:nth-child(3)'); // Hiligaynon button
const bicolanoBtn = document.querySelector('.quiz-btn:nth-child(4)'); // Bicolano button
const kapampanganBtn = document.querySelector('.quiz-btn:nth-child(5)'); // Kapampangan button
const quizContainer = document.getElementById('quizContainer');
const wordDisplay = document.getElementById('wordDisplay');
const optionsContainer = document.getElementById('optionsContainer');
const nextBtn = document.getElementById('nextBtn');
const title = document.querySelector('.title');
const subtitle = document.querySelector('.subtitle');
const quizButtons = document.querySelector('.quiz-buttons');

let currentQuestion = 0;
let score = 0;
let selectedAnswer = null;
let currentQuestions;

// Sample Cebuano quiz data (word: Cebuano, correct meaning index)
const questionsCebuano = [
  {
    word: "Gwapa",
    options: ["Maganda", "Masama", "Pangit", "Maliit"],
    correct: 0,
    trivia: "The word 'Gwapa' is used to describe someone who is beautiful or attractive. It is often used in casual conversations, compliments, or when talking about someone's looks."
  },
  {
    word: "Dili",
    options: ["Oo", "Siguro", "Hindi", "Palagi"],
    correct: 2,
    trivia: "'Dili' means 'no' or 'not' in Cebuano, used to express negation in sentences or direct responses."
  },
  {
    word: "Maayong Buntag",
    options: ["Magandang Araw", "Magandang Umaga", "Magandang Hapon", "Magandang Gabi"],
    correct: 1,
    trivia: "'Maayong Buntag' is the Cebuano greeting for 'Good Morning', commonly used to start the day politely."
  },
  {
    word: "Lami",
    options: ["Maasim", "Mapait", "Maanghang", "Masarap"],
    correct: 3,
    trivia: "'Lami' means 'delicious' or 'tasty' in Cebuano, often used to compliment food or describe pleasant flavors."
  },
  {
    word: "Mangaon ta",
    options: ["Kain tayo", "Alis tayo", "Busog pa ako", "Gutom na ako"],
    correct: 0,
    trivia: "'Mangaon ta' is a Bisaya phrase from the Philippines that means 'Let's eat!'. It's a common and friendly invitation to share a meal with loved ones or others."
  }
];

// Sample Tagalog quiz data (word: Tagalog, correct meaning index)
const questionsTagalog = [
  {
    word: "Maganda",
    options: ["Beautiful", "Ugly", "Small", "Big"],
    correct: 0,
    trivia: "The word 'Maganda' means 'beautiful' or 'pretty' in Tagalog, commonly used to compliment appearance or things."
  },
  {
    word: "Kumusta",
    options: ["Hello", "Goodbye", "How are you", "Thank you"],
    correct: 2,
    trivia: "'Kumusta' is a Tagalog greeting meaning 'How are you?', used to inquire about someone's well-being."
  },
  {
    word: "Salamat",
    options: ["Please", "Sorry", "Thank you", "Excuse me"],
    correct: 2,
    trivia: "'Salamat' means 'thank you' in Tagalog, a polite expression of gratitude."
  },
  {
    word: "Bahay",
    options: ["House", "Car", "School", "Food"],
    correct: 0,
    trivia: "'Bahay' translates to 'house' or 'home' in Tagalog, referring to a place of residence."
  },
  {
    word: "Kain tayo",
    options: ["Let's eat", "Let's sleep", "Let's go", "Let's play"],
    correct: 0,
    trivia: "'Kain tayo' means 'Let's eat' in Tagalog, an invitation to share a meal."
  }
];

// Sample Hiligaynon quiz data (word: Hiligaynon, correct meaning index)
const questionsHiligaynon = [
  {
    word: "Palangga",
    options: ["Kaibigan", "Minamahal", "Bata", "Damit"],
    correct: 1,
    trivia: "'Palangga' is a word from various Philippine languages, particularly Hiligaynon and Bisaya, that means 'love,' 'beloved,' or 'my love,' and is used as a term of endearment to express affection for someone dear."
  },
  {
    word: "Amigo",
    options: ["Kaibigan", "Tubig", "Salamat", "Masaya"],
    correct: 0,
    trivia: "'Amigo' means friend (male), while 'Amiga' is used for female friends. Both are borrowed from Spanish."
  },
  {
    word: "Pagkaon",
    options: ["Balay", "Tulog", "Bayo", "Pagkain"],
    correct: 3,
    trivia: "'Pagkaon' means food, the things we eat. It comes from the root word kaon."
  },
  {
    word: "Asta sa liwat",
    options: ["Hindi", "Maganda Gabi", "Hanggang sa muli", "Oo"],
    correct: 2,
    trivia: "'Asta' sa liwat means 'See you again' or 'Until next time' in Hiligaynon."
  },
  {
    word: "Balay",
    options: ["Bahay", "Maganda", "Salamat", "Kaibigan"],
    correct: 0,
    trivia: "'Balay' is a word with origins in Austronesian languages, means 'House' or 'Home', the place where a family lives."
  }
]

// Sample Bicolano quiz data (word: Bicolano, correct meaning index)
const questionsBicolano = [
  {
    word: "Marhay na aldaw",
    options: ["Magandang umaga", "Magandang hapon", "Magandang gabi", "Magandang araw"],
    correct: 3,
    trivia: "'Marhay na aldaw' is a common Bicolano greeting meaning 'Good day'."
  },
  {
    word: "Daraga",
    options: ["Babae o dalaga", "Patawad", "Kaibigan", "Salamat"],
    correct: 0,
    trivia: "'Daraga' means lady or unmarried young woman. The famous Mayon Volcano is in Legazpi, Albay, which was once called Ciudad de Nueva Caceres de Daraga."
  },
  {
    word: "Pangadyi",
    options: ["Pagkain", "Panalangin", "Kaibigan", "Bahay"],
    correct: 1,
    trivia: "'Pangadyi' means 'prayer' in Bicolano, often used in religious contexts."
  },
  {
    word: "Harayo",
    options: ["Malayo", "Malapit", "Sa loob", "Sa labas"],
    correct: 0,
    trivia: "'Harayo' means 'far' or 'distant' in Bicolano."
  },
  {
    word: "Kaigwa",
    options: ["Kapitbahay", "Estranghero", "Kaibigan", "Kaaway"],
    correct: 2,
    trivia: "'Kaigwa' means 'friend' in Bicolano."
  }
];

// Sample Kapampangan quiz data (word: Kapampangan, correct meaning index)
const questionsKapampangan = [
  {
    word: "Mayaus",
    options: ["Matalino", "Mabait", "Maganda", "Malakas"],
    correct: 2,
    trivia: "'Mayaus' means 'beautiful' in Kapampangan."
  },
  {
    word: "Mayap a bengi",
    options: ["Magandang umaga", "Magandang hapon", "Magandang gabi", "Paalam"],
    correct: 2,
    trivia: "'Mayap a bengi' means good evening. Mayap = good, bengi = night/evening."
  },
  {
    word: "Dakal a salamat",
    options: ["Magandang umaga", "Maraming salamat", "Paalam", "Pakiusap"],
    correct: 1,
    trivia: "'Dakal a salamat' means 'thank you very much' in Kapampangan."
  },
  {
    word: "Balen",
    options: ["Lalaki", "Kaibigan", "Pamilya", "Bahay"],
    correct: 3,
    trivia: "'Balen' means 'house' in Kapampangan."
  },
  {
    word: "Mangan tamu",
    options: ["Kain na tayo", "Matulog na tayo", "Tara na", "Tara laro tayo"],
    correct: 0,
    trivia: "'Mangan tamu' means 'let's eat' in Kapampangan."
  }
];

function startQuiz(dialect) {
  quizButtons.style.display = 'none';
  title.textContent = `${dialect} Quiz`;
  subtitle.textContent = 'Choose the correct meaning';
  quizContainer.style.display = 'flex';
  currentQuestion = 0;
  score = 0;
  if (dialect === 'Cebuano') {
    currentQuestions = questionsCebuano;
  } else if (dialect === 'Tagalog') {
    currentQuestions = questionsTagalog;
  } else if (dialect === 'Hiligaynon') {
    currentQuestions = questionsHiligaynon
  } else if (dialect === 'Bicolano') {
    currentQuestions = questionsBicolano;
  } else if (dialect === 'Kapampangan') {
    currentQuestions = questionsKapampangan;
  }
  displayQuestion();
}

cebuanoBtn.addEventListener('click', () => startQuiz('Cebuano'));
tagalogBtn.addEventListener('click', () => startQuiz('Tagalog'));
hiligaynonBtn.addEventListener('click', () => startQuiz('Hiligaynon'));
bicolanoBtn.addEventListener('click', () => startQuiz('Bicolano'));
kapampanganBtn.addEventListener('click', () => startQuiz('Kapampangan'));

function displayQuestion() {
  const q = currentQuestions[currentQuestion];
  wordDisplay.textContent = q.word;
  optionsContainer.innerHTML = '';
  selectedAnswer = null;
  nextBtn.style.display = 'none';

  // Remove existing trivia if present
  const existingTrivia = quizContainer.querySelector('.trivia-box');
  if (existingTrivia) {
    existingTrivia.remove();
  }

  // Remove existing feedback if present
  const existingFeedback = quizContainer.querySelector('.feedback');
  if (existingFeedback) {
    existingFeedback.remove();
  }

  q.options.forEach((option, index) => {
    const btn = document.createElement('button');
    btn.className = 'option-btn';
    btn.textContent = option;
    btn.addEventListener('click', () => checkAnswer(index));
    optionsContainer.appendChild(btn);
  });
}

function createConfetti() {
  const colors = ['#FFC700', '#FF0000', '#2E3192', '#41BBC7', '#7F8C8D', '#E67E22', '#9B59B6'];
  const confettiCount = 30;
  const confettiContainer = document.createElement('div');
  confettiContainer.style.position = 'fixed';
  confettiContainer.style.top = '50%';
  confettiContainer.style.left = '50%';
  confettiContainer.style.transform = 'translate(-50%, -50%)';
  confettiContainer.style.width = '0';
  confettiContainer.style.height = '0';
  confettiContainer.style.pointerEvents = 'none';
  confettiContainer.style.zIndex = '9999';

  for (let i = 0; i < confettiCount; i++) {
    const confetti = document.createElement('div');
    confetti.classList.add('confetti-piece');
    confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
    confetti.style.width = (5 + Math.random() * 10) + 'px';
    confetti.style.height = confetti.style.width;
    const angle = Math.random() * 2 * Math.PI;
    const distance = 100 + Math.random() * 200;
    const x = Math.cos(angle) * distance;
    const y = Math.sin(angle) * distance;
    confetti.style.setProperty('--x', x + 'px');
    confetti.style.setProperty('--y', y + 'px');
    confetti.style.animationName = 'confetti-pop';
    confetti.style.animationDuration = (1 + Math.random() * 2) + 's';
    confetti.style.animationDelay = Math.random() * 0.5 + 's';
    confettiContainer.appendChild(confetti);
  }

  document.body.appendChild(confettiContainer);

  setTimeout(() => {
    confettiContainer.remove();
  }, 3000);
}

function checkAnswer(selectedIndex) {
  if (selectedAnswer !== null) return; // Prevent multiple clicks
  selectedAnswer = selectedIndex;

  const q = currentQuestions[currentQuestion];
  const buttons = optionsContainer.querySelectorAll('.option-btn');

  buttons.forEach((btn, index) => {
    btn.disabled = true;
    if (index === q.correct) {
      btn.classList.add('correct');
    } else if (index === selectedIndex && index !== q.correct) {
      btn.classList.add('incorrect');
    }
  });

  if (selectedIndex === q.correct) {
    score++;
    createConfetti();

    setTimeout(() => {
      nextBtn.style.display = 'block';
      if (currentQuestion === currentQuestions.length - 1) {
        nextBtn.textContent = 'Done';
      }

      // Show trivia for correct answer
      const triviaDiv = document.createElement('div');
      triviaDiv.className = 'trivia-box';
      triviaDiv.innerHTML = `<p><strong>Trivia:</strong> ${q.trivia}</p>`;
      quizContainer.appendChild(triviaDiv);

      // Show "Correct!" feedback
      const feedbackDiv = document.createElement('div');
      feedbackDiv.className = 'feedback';
      feedbackDiv.style.color = '#4CAF50'; // green color
      feedbackDiv.innerHTML = 'Correct! <span class="icon">✅</span>';
      quizContainer.appendChild(feedbackDiv);
    }, 1500);
  } else {
    setTimeout(() => {
      nextBtn.style.display = 'block';
      if (currentQuestion === currentQuestions.length - 1) {
        nextBtn.textContent = 'Done';
      }

      // Show "Wrong" feedback
      const feedbackDiv = document.createElement('div');
      feedbackDiv.className = 'feedback';
      feedbackDiv.style.color = '#f44336'; // red color
      feedbackDiv.innerHTML = 'Wrong <span class="icon">❌</span>';
      quizContainer.appendChild(feedbackDiv);
    }, 1500);
  }
}

nextBtn.addEventListener('click', () => {
  currentQuestion++;
  if (currentQuestion < currentQuestions.length) {
    displayQuestion();
  } else {
    endQuiz();
  }
});

function endQuiz() {
  quizContainer.innerHTML = `
    <h2>Quiz Complete!</h2>
    <p>Your score: ${score} / ${currentQuestions.length}</p>
    <button onclick="location.reload()" class="next-btn">Play Again</button>
  `;
  subtitle.textContent = 'Keep it up!';

const history = JSON.parse(localStorage.getItem("userHistory")) || [];
const now = new Date().toLocaleString();
history.unshift(`[${now}] Completed quiz: ${title.textContent} — Score: ${score}/${currentQuestions.length}`);
if (history.length > 10) history.pop(); 
localStorage.setItem("userHistory", JSON.stringify(history));

}
