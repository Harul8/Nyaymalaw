'use strict';

// THE ADVOCATE'S INITIALS: one rule for the app's person button and the website's account bar (plans
// AN.20 and AN.22), so the two can never disagree. The first letters of the first and last words of the
// name the account holds - after any title such as Adv. or Dr. When the account holds no name the button
// shows its email, which is one word, and so one letter. Nothing the page made up.
window.NmPerson = (() => {
  const TITLES = /^(adv|advocate|dr|mr|mrs|ms|miss|shri|smt|sri|prof|justice|hon)\.?$/i;

  function initialsOf(name) {
    const first = (word) => (Array.from(word).find((ch) => /[\p{L}\p{N}]/u.test(ch)) || '').toLocaleUpperCase();
    const words = String(name || '').trim().split(/\s+/).filter(Boolean);
    while (words.length > 1 && TITLES.test(words[0])) words.shift();
    return [words[0] || '', words.length > 1 ? words[words.length - 1] : ''].map(first).join('');
  }

  return Object.freeze({ initialsOf });
})();
