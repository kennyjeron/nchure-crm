// Copy this file to js/firebase-config.js and replace every placeholder.
// Firebase Web configuration is client-visible by design; never put Admin SDK
// credentials, service-account JSON, database passwords, or private API secrets here.
export const firebaseConfig = Object.freeze({
  apiKey: "REPLACE_WITH_FIREBASE_WEB_API_KEY",
  authDomain: "REPLACE_WITH_PROJECT_ID.firebaseapp.com",
  projectId: "REPLACE_WITH_FIREBASE_PROJECT_ID",
  storageBucket: "REPLACE_WITH_PROJECT_ID.firebasestorage.app",
  messagingSenderId: "REPLACE_WITH_SENDER_ID",
  appId: "REPLACE_WITH_FIREBASE_APP_ID"
});
