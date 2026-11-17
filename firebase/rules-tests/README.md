# Firestore Rules tests

These tests use the Firebase Emulator Suite and `@firebase/rules-unit-testing`.

## Run

1. From the repository root, copy `firebase/firebase.json.example` to
   `firebase.json` (the root `firebase.json` is local and ignored by Git).
2. From this directory:

   ```sh
   npm install
   npm test
   ```

The test command starts the Firestore emulator, runs role-isolation checks, and
stops the emulator. It uses the demo project ID `demo-nchure-crm`; no live Firebase
project is contacted.

## Cases covered

- Founder can read finance records.
- Sales staff can query assigned leads but cannot read another owner's lead.
- Sales staff cannot read expenses.
- Client portal users can only read their own invoice.
- A user cannot change their own role to Founder.
- Inactive profiles cannot access CRM records.

These are baseline tests, not full application acceptance tests. Add coverage for
every collection, each supported role, create/update/delete paths, query constraints,
and account provisioning before production cutover.
