INSERT INTO subject_enrollments (student_id, subject_id, enrolled_at)
SELECT
    users.id,
    subjects.id,
    NOW()
FROM users
INNER JOIN subjects
    ON subjects.organization_id = users.organization_id
WHERE LOWER(users.role) = 'student'
  AND NOT EXISTS (
      SELECT 1
      FROM subject_enrollments
      WHERE subject_enrollments.student_id = users.id
        AND subject_enrollments.subject_id = subjects.id
  );
