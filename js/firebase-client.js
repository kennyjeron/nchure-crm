// NCHURE CRM Firebase Spark foundation.
// Pinned to the current modular Web SDK version documented by Firebase.
// This module is intentionally not imported by index.html yet: the existing
// UI still calls the FastAPI /api endpoints. Do not deploy until the adapter
// migration and the Security Rules tests are complete.
import { firebaseConfig } from "./firebase-config.js";

import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/13.3.0/firebase-app.js";
import {
  getAuth,
  setPersistence,
  browserLocalPersistence,
  signInWithEmailAndPassword,
  signOut,
  createUserWithEmailAndPassword,
  sendPasswordResetEmail,
  reauthenticateWithCredential,
  EmailAuthProvider,
  updatePassword
} from "https://www.gstatic.com/firebasejs/13.3.0/firebase-auth.js";
import {
  getFirestore,
  doc,
  collection,
  getDoc,
  getDocs,
  query,
  where,
  orderBy,
  limit,
  setDoc,
  updateDoc,
  deleteDoc,
  serverTimestamp,
  writeBatch,
  runTransaction
} from "https://www.gstatic.com/firebasejs/13.3.0/firebase-firestore.js";

const requiredConfig = ["apiKey", "authDomain", "projectId", "appId"];
const missing = requiredConfig.filter((key) => {
  const value = firebaseConfig?.[key];
  return !value || String(value).startsWith("REPLACE_");
});
if (missing.length) {
  throw new Error(
    "NCHURE Firebase is not configured. Copy js/firebase-config.example.js to " +
    "js/firebase-config.js and fill: " + missing.join(", ")
  );
}

const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
const auth = getAuth(app);
const db = getFirestore(app);
await setPersistence(auth, browserLocalPersistence);

const ORG_ID = "nchure";
const userDoc = (uid) => doc(db, "organizations", ORG_ID, "users", uid);
const records = (name) => collection(db, "organizations", ORG_ID, name);

async function getCurrentProfile() {
  const currentUser = auth.currentUser;
  if (!currentUser) throw new Error("Authentication required.");
  const snapshot = await getDoc(userDoc(currentUser.uid));
  if (!snapshot.exists()) {
    await signOut(auth);
    throw new Error("This account has no NCHURE CRM profile. Ask the Founder to activate it.");
  }
  const profile = snapshot.data();
  if (profile.active !== true) {
    await signOut(auth);
    throw new Error("This NCHURE CRM account is disabled.");
  }
  return { id: currentUser.uid, ...profile, email: currentUser.email || profile.email || "" };
}

async function signIn(email, password) {
  const result = await signInWithEmailAndPassword(auth, String(email).trim().toLowerCase(), password);
  try {
    const profile = await getCurrentProfile();
    return { user: { id: profile.id, name: profile.name, email: profile.email, role: profile.role } };
  } catch (error) {
    await signOut(auth);
    throw error;
  }
}

async function signOutCurrentUser() {
  await signOut(auth);
}

async function changeOwnPassword(currentPassword, newPassword) {
  const user = auth.currentUser;
  if (!user || !user.email) throw new Error("Authentication required.");
  if (String(newPassword || "").length < 14) {
    throw new Error("New password must be at least 14 characters.");
  }
  const credential = EmailAuthProvider.credential(user.email, currentPassword);
  await reauthenticateWithCredential(user, credential);
  await updatePassword(user, newPassword);
  return { ok: true };
}

async function sendPasswordReset(email) {
  const normalized = String(email || "").trim().toLowerCase();
  if (!normalized) throw new Error("A valid email address is required.");
  await sendPasswordResetEmail(auth, normalized);
  return { ok: true };
}

// Provisioning uses a secondary Auth app so a Founder remains signed in while
// creating a team or client account. Firestore profile creation must still be
// performed by the signed-in manager and is protected by firestore.rules.
async function createAuthAccount(email, password) {
  const secondaryName = "nchure-user-provisioning";
  const secondaryApp = getApps().find((item) => item.name === secondaryName)
    || initializeApp(firebaseConfig, secondaryName);
  const secondaryAuth = getAuth(secondaryApp);
  try {
    const credential = await createUserWithEmailAndPassword(
      secondaryAuth,
      String(email).trim().toLowerCase(),
      password
    );
    const newUid = credential.user.uid;
    await signOut(secondaryAuth);
    return { uid: newUid };
  } catch (error) {
    await signOut(secondaryAuth).catch(() => {});
    throw error;
  }
}

async function readRecordList(collectionName, filters = [], sortField = "createdAt", maxItems = 500) {
  const allowed = new Set([
    "clients", "leads", "projects", "milestones", "tasks", "quotations",
    "invoices", "payments", "expenses", "tickets", "documents", "approvals",
    "meetings", "messages", "audit", "aiChats", "notifications"
  ]);
  if (!allowed.has(collectionName)) throw new Error("Unsupported CRM collection.");
  const constraints = filters.map(([field, operator, value]) => where(field, operator, value));
  constraints.push(orderBy(sortField, "desc"), limit(Math.min(Math.max(maxItems, 1), 500)));
  const result = await getDocs(query(records(collectionName), ...constraints));
  return result.docs.map((item) => ({ id: item.id, ...item.data() }));
}

async function saveRecord(collectionName, recordId, data, merge = false) {
  const reference = doc(db, "organizations", ORG_ID, collectionName, String(recordId));
  const payload = { ...data, updatedAt: serverTimestamp() };
  await setDoc(reference, payload, { merge });
  return { id: String(recordId), ...payload };
}

async function removeRecord(collectionName, recordId) {
  await deleteDoc(doc(db, "organizations", ORG_ID, collectionName, String(recordId)));
  return { ok: true, id: String(recordId) };
}

async function getSettings(settingId = "public") {
  const snapshot = await getDoc(doc(db, "organizations", ORG_ID, "settings", settingId));
  return snapshot.exists() ? snapshot.data() : null;
}

window.NCHURE_FIREBASE = Object.freeze({
  app,
  auth,
  db,
  orgId: ORG_ID,
  userDoc,
  records,
  getCurrentProfile,
  signIn,
  signOut: signOutCurrentUser,
  changeOwnPassword,
  sendPasswordReset,
  createAuthAccount,
  readRecordList,
  saveRecord,
  removeRecord,
  getSettings,
  firestore: {
    doc, collection, getDoc, getDocs, query, where, orderBy, limit,
    setDoc, updateDoc, deleteDoc, serverTimestamp, writeBatch, runTransaction
  }
});

window.dispatchEvent(new CustomEvent("nchure:firebase-ready"));
