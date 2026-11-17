import { readFile } from "node:fs/promises";
import { after, before, beforeEach, test } from "node:test";
import assert from "node:assert/strict";

import {
  initializeTestEnvironment,
  assertFails,
  assertSucceeds
} from "@firebase/rules-unit-testing";

import {
  collection,
  doc,
  getDoc,
  getDocs,
  query,
  setDoc,
  updateDoc,
  where
} from "firebase/firestore";

const PROJECT_ID = "demo-nchure-crm";
const ORG = "nchure";
let testEnv;

const path = (...parts) => parts.join("/");

before(async () => {
  const rules = await readFile(new URL("../firestore.rules", import.meta.url), "utf8");
  testEnv = await initializeTestEnvironment({
    projectId: PROJECT_ID,
    firestore: { rules }
  });
});

beforeEach(async () => {
  await testEnv.clearFirestore();
  await testEnv.withSecurityRulesDisabled(async (context) => {
    const db = context.firestore();
    const seed = [
      ["organizations", ORG, "users", "founder-uid", {
        name: "Founder", email: "founder@example.com", role: "Founder", active: true
      }],
      ["organizations", ORG, "users", "sales-uid", {
        name: "Sales User", email: "sales@example.com", role: "Sales Executive", active: true
      }],
      ["organizations", ORG, "users", "client-uid", {
        name: "Client User", email: "client@example.com", role: "Client", active: true, clientId: "client-a"
      }],
      ["organizations", ORG, "users", "inactive-uid", {
        name: "Inactive User", email: "inactive@example.com", role: "Sales Executive", active: false
      }],
      ["organizations", ORG, "leads", "lead-owned", {
        name: "Assigned lead", assignedToUid: "sales-uid", createdAt: new Date()
      }],
      ["organizations", ORG, "leads", "lead-other", {
        name: "Other lead", assignedToUid: "another-user", createdAt: new Date()
      }],
      ["organizations", ORG, "expenses", "expense-1", {
        title: "Private expense", amount: 1000, createdAt: new Date()
      }],
      ["organizations", ORG, "invoices", "invoice-a", {
        number: "INV-A", clientId: "client-a", clientUid: "client-uid", createdAt: new Date()
      }],
      ["organizations", ORG, "invoices", "invoice-b", {
        number: "INV-B", clientId: "client-b", clientUid: "another-client", createdAt: new Date()
      }]
    ];
    for (const [ ...segments, data ] of seed) {
      await setDoc(doc(db, path(...segments)), data);
    }
  });
});

after(async () => {
  await testEnv?.cleanup();
});

test("Founder can read finance records", async () => {
  const db = testEnv.authenticatedContext("founder-uid").firestore();
  await assertSucceeds(getDoc(doc(db, "organizations", ORG, "expenses", "expense-1")));
});

test("Sales member can query assigned leads but not another member's lead", async () => {
  const db = testEnv.authenticatedContext("sales-uid").firestore();
  const assignedQuery = query(
    collection(db, "organizations", ORG, "leads"),
    where("assignedToUid", "==", "sales-uid")
  );
  const result = await assertSucceeds(getDocs(assignedQuery));
  assert.equal(result.size, 1);
  await assertFails(getDoc(doc(db, "organizations", ORG, "leads", "lead-other")));
});

test("Sales member cannot read finance records", async () => {
  const db = testEnv.authenticatedContext("sales-uid").firestore();
  await assertFails(getDoc(doc(db, "organizations", ORG, "expenses", "expense-1")));
});

test("Client can read only their own invoice", async () => {
  const db = testEnv.authenticatedContext("client-uid").firestore();
  await assertSucceeds(getDoc(doc(db, "organizations", ORG, "invoices", "invoice-a")));
  await assertFails(getDoc(doc(db, "organizations", ORG, "invoices", "invoice-b")));
});

test("User cannot promote their own role", async () => {
  const db = testEnv.authenticatedContext("sales-uid").firestore();
  await assertFails(
    updateDoc(doc(db, "organizations", ORG, "users", "sales-uid"), { role: "Founder" })
  );
});

test("Inactive user cannot access workspace records", async () => {
  const db = testEnv.authenticatedContext("inactive-uid").firestore();
  await assertFails(getDoc(doc(db, "organizations", ORG, "leads", "lead-owned")));
});
