# NCHURE CRM Firestore data model

This is the target data contract for the Spark migration. It is deliberately
record-oriented. Do **not** copy the old `crm_dashboard_state` JSON snapshot
into one Firestore document: the old API allowed up to 2 MB, while Firestore
documents have a 1 MiB limit and document-level Security Rules cannot conceal
sensitive fields inside an array.

## Paths

- `organizations/nchure/users/{firebaseAuthUid}` — user profile and role.
- `organizations/nchure/settings/public` — non-sensitive company display settings.
- `organizations/nchure/settings/private` — private business settings; manager-only.
- `organizations/nchure/{collection}/{recordId}` — one document per CRM record.

Target collections map the existing UI arrays as follows:

| Existing UI key | Firestore collection |
|---|---|
| clients | clients |
| leads | leads |
| projects | projects |
| milestones | milestones |
| tasks | tasks |
| quotations | quotations |
| invoices | invoices |
| payments | payments |
| expenses | expenses |
| tickets | tickets |
| documents | documents |
| approvals | approvals |
| meetings | meetings |
| messages | messages |
| audit | audit |
| aiChats | aiChats |
| notifications | notifications |

## Required identity fields

Any record that is visible to or writable by a non-manager must carry stable Firebase
Auth UIDs. The UI currently stores several assignments as display names; those
strings are not sufficient for database authorization.

- `createdByUid`: creator's Firebase Auth UID.
- `assignedToUid`: assigned team member's Firebase Auth UID.
- `ownerUid`: owning user for private notifications and AI chats.
- `uploadedByUid`: uploader UID for documents.
- `participantUids`, `memberUids`, `attendeeUids`: arrays of Firebase Auth UIDs.
- `clientUid`: Firebase Auth UID for a client portal user.
- `clientId`: stable client record ID for related records.

Every client-side query must include filters that satisfy the Firestore Security
Rules for restricted roles. Firestore rules reject unauthorized query result sets;
they do not filter out unauthorized documents after the query.

## User document

```json
{
  "name": "NCHURE Founder",
  "email": "founder@example.com",
  "role": "Founder",
  "active": true,
  "dept": "Management",
  "phone": "",
  "skills": [],
  "joined": "2026-11-17",
  "createdAt": "<Firestore Timestamp>"
}
```

The document ID is the Firebase Auth UID. Roles are profile data protected by
Firestore Rules, never a field users may change in their own profile.

## Migration rules

1. Never import the old `crm_dashboard_state` as one public document.
2. Map every record to a separate Firestore document and normalize assignment
   fields to UIDs before allowing non-manager access.
3. Keep finance collections separate from sales, support and project collections.
4. Do not migrate password hashes. Firebase Authentication owns password
   credentials after cutover; all users will need newly provisioned Firebase
   Auth accounts or password reset.
5. The current Supabase audit reported zero rows across 17 public tables,
   zero `auth.users`, zero Storage objects and zero Storage buckets. This is
   not proof that browser localStorage is empty. Export browser state before cutover.
6. Firestore's 1 MiB per-document limit means very large records or file blobs
   must not be embedded in a record document. File storage is not part of the
   strict Spark baseline.
