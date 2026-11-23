"""
`python manage.py seed_demo`: realistic demo data for local development and the course demo.

- Runs only when DEBUG is True (never on a production settings file).
- Safe to run again: everything is looked up first and created only if missing; a complaint
  that already exists (same student and title) is left exactly as it is.
- Keeps the existing demo accounts (demo.admin@uol.edu.pk, demo.advisor@uol.edu.pk,
  12345678@student.uol.edu.pk) and the "DEMO — Fall 2026" batch.
- Complaints, status changes, responses, owner changes and student actions go only through
  complaints.services, and Student Voice only through voice.services, so their history and
  notifications are the real ones. Only the clock
  is simulated: each step runs with django.utils.timezone.now set to a moment in the past few
  weeks, so lists, "Oldest first", "Next complaint" and the Overview counts look realistic.
"""

from datetime import date, timedelta
from unittest import mock

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from academics import services as academic_services
from academics.models import AcademicTerm, Batch, Section, Semester
from accounts import identity
from accounts import services as account_services
from accounts.models import AdvisorAssignment, StudentProfile, User
from complaints import services
from complaints.models import Complaint, ComplaintCategory
from notifications import services as notification_services
from notifications.models import Notification
from voice import services as voice_services
from voice.models import Submission

BATCH_NAME = "DEMO — Fall 2026"
OLD_BATCH_NAMES = ("DEMO ? Fall 2026",)  # the same batch, saved earlier without its em dash
TERM = ("Fall 2026", date(2026, 9, 1), date(2027, 1, 15))
ADMIN = ("demo.admin@uol.edu.pk", "Demo Super Admin")
ADVISORS = [("demo.advisor@uol.edu.pk", "Dr. Ayesha Rahman"), ("demo.advisor2@uol.edu.pk", "Dr. Kamran Siddiqui")]
DEMO_STUDENT = "12345678@student.uol.edu.pk"
CATEGORIES = ["Academic", "Non-academic", "Personal/Wellbeing", "Other"]

STUDENTS = {
    "DEMO-A": [
        (DEMO_STUDENT, "Ali Khan"),
        ("70126001@student.uol.edu.pk", "Fatima Noor"),
        ("70126002@student.uol.edu.pk", "Hassan Raza"),
        ("70126003@student.uol.edu.pk", "Zainab Ahmed"),
        ("70126004@student.uol.edu.pk", "Usman Tariq"),
        ("70126005@student.uol.edu.pk", "Ayesha Siddiqa"),
    ],
    "DEMO-B": [
        ("70126006@student.uol.edu.pk", "Bilal Ahmad"),
        ("70126007@student.uol.edu.pk", "Sana Iqbal"),
        ("70126008@student.uol.edu.pk", "Hamza Sheikh"),
        ("70126009@student.uol.edu.pk", "Maryam Javed"),
        ("70126010@student.uol.edu.pk", "Omar Farooq"),
        ("70126011@student.uol.edu.pk", "Hira Malik"),
    ],
}
# Who handles each section's complaints in the script below.
SECTION_ADVISOR = {"DEMO-A": "demo.advisor@uol.edu.pk", "DEMO-B": "demo.advisor2@uol.edu.pk"}

# (student email, category, title, description, steps). Each step: (days ago, action, text).
# Actions: review, respond, resolve, reject, still (student: still not resolved), info (student:
# further information), cancel (student: cancellation request), owner (Super Admin assigns the
# section's advisor), admin_respond.
COMPLAINTS = [
    (DEMO_STUDENT, "Academic", "Lab timetable clashes with Data Structures lecture",
     "The Tuesday 11:00 Operating Systems lab overlaps the Data Structures lecture for Section DEMO-A, so we miss one every week.",
     [(18, "review", "Checking the timetable with the department."),
      (16, "respond", "The timetable office has been asked to move the lab."),
      (2, "resolve", "The lab moved to Thursday 14:00 from next week.")]),
    (DEMO_STUDENT, "Non-academic", "Projector in Room 204 not working",
     "The projector in Room 204 has not worked for two weeks; lecturers use the whiteboard only.",
     [(9, "review", ""), (8, "respond", "Maintenance has a ticket open; a replacement lamp is on order.")]),
    (DEMO_STUDENT, "Other", "Request for an extra library slot on Saturdays",
     "Could the library stay open on Saturday afternoons during the exam weeks?",
     [(6, "reject", "Library hours are set by the main campus and cannot be changed for one department this term.")]),
    (DEMO_STUDENT, "Personal/Wellbeing", "Need a quiet space for prayer between classes",
     "There is no quiet room near the CS block between the 13:00 and 14:00 classes.",
     []),
    ("70126001@student.uol.edu.pk", "Academic", "Quiz 2 marks missing on the portal",
     "My Quiz 2 marks for Discrete Mathematics are not on the portal, though others in my section have theirs.",
     [(14, "review", ""), (13, "resolve", "The marks were uploaded; please check again."),
      (12, "still", "They still show as absent."), (11, "respond", "Asked the instructor to correct the attendance flag.")]),
    ("70126002@student.uol.edu.pk", "Non-academic", "Water cooler on the second floor is empty",
     "The second-floor water cooler has been empty since Monday.",
     [(4, "resolve", "Refilled, and added to the daily maintenance checklist.")]),
    ("70126003@student.uol.edu.pk", "Personal/Wellbeing", "Stress about the assignment deadlines",
     "Three major assignments are due in the same week. Is there any support available?",
     [(7, "review", ""), (6, "respond", "You can book a session with the student counsellor; I have also raised the clash with your instructors.")]),
    ("70126004@student.uol.edu.pk", "Other", "Parking stickers not issued yet",
     "Students who paid for parking in September have not received their stickers.",
     [(3, "info", "I paid on 5 September; the receipt number is 4417.")]),
    ("70126005@student.uol.edu.pk", "Academic", "Course outline for Probability not shared",
     "We are in week 9 and have not received the Probability course outline.",
     [(20, "owner", ""), (19, "review", ""), (1, "resolve", "The outline has been shared on the course page.")]),
    ("70126006@student.uol.edu.pk", "Academic", "Re-check request for the mid-term paper",
     "I believe Question 4 of my Linear Algebra mid-term was not marked.",
     [(10, "review", ""), (9, "respond", "Your paper is with the instructor for re-checking.")]),
    ("70126007@student.uol.edu.pk", "Non-academic", "Washroom on the ground floor needs repair",
     "The tap in the ground-floor washroom keeps running and the floor is always wet.",
     [(2, "resolve", "The plumber replaced the tap.")]),
    ("70126008@student.uol.edu.pk", "Other", "Request to change my elective",
     "I would like to move from Technical Writing to Entrepreneurship.",
     [(8, "reject", "Elective changes closed in week 2, as announced. Please talk to me about next semester.")]),
    ("70126009@student.uol.edu.pk", "Personal/Wellbeing", "Harassment in the transport bus",
     "A group of students from another department makes comments on the evening bus.",
     [(5, "owner", ""), (5, "review", "Taking this seriously; I will contact you privately."),
      (4, "admin_respond", "The Super Admin office has informed campus security.")]),
    ("70126010@student.uol.edu.pk", "Academic", "Practical exam date not announced",
     "The Database Systems practical exam date is still not announced.",
     [(1, "cancel", "The date was announced in class today.")]),
    ("70126011@student.uol.edu.pk", "Non-academic", "Cafeteria prices increased without notice",
     "Tea and sandwich prices went up by 30% this week without any notice.",
     [(6, "reject", "Cafeteria pricing is handled by the vendor contract, not by Student Affairs.")]),
]

# Student Voice: (student email, type, text, days ago, action, days ago of the action, reply).
# Actions: answer (Question or reply), review (mark reviewed), None (still waiting).
VOICE_SUBMISSIONS = [
    (DEMO_STUDENT, "question", "When will the final exam date sheet for Semester 4 be published?",
     6, "answer", 1, "The date sheet will be published on the department notice board by the end of this week."),
    (DEMO_STUDENT, "idea", "Could we have a short peer tutoring hour for Data Structures before each quiz?",
     5, "answer", 3, "A good idea. I will discuss a trial with the course instructor."),
    (DEMO_STUDENT, "feedback", "The new lab assistant explains the linked list tasks very clearly.",
     2, None, None, ""),
    ("70126001@student.uol.edu.pk", "idea", "A shared calendar of assignment deadlines would help us plan our weeks.",
     7, "review", 5, ""),
    ("70126003@student.uol.edu.pk", "question", "Can a student take a course from a higher semester to reduce load later?",
     1, None, None, ""),
    ("70126006@student.uol.edu.pk", "feedback", "The extra revision class before the mid-terms was really useful.",
     9, "answer", 8, "Thank you. I have passed this on to the instructor."),
    ("70126008@student.uol.edu.pk", "question", "Is attendance counted during the week of the department sports gala?",
     4, "answer", 2, "Yes, regular classes continue and attendance is counted as usual."),
    ("70126010@student.uol.edu.pk", "idea", "Please add more charging points in the second floor study area.",
     3, "review", 2, ""),
]


class Command(BaseCommand):
    help = "Create demo data for local development (DEBUG only). Safe to run again."

    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("seed_demo only runs when DEBUG is True. It is for local demo data only.")
        self.created = []
        self.now = timezone.now()
        with transaction.atomic():
            structure = self._structure()
            people = self._people(structure)
            self._demo_staff(structure, people)
            created_demo_complaints = self._complaints(structure, people)
            self._voice(people)
            if created_demo_complaints:
                self._mark_older_updates_read(people["students"][DEMO_STUDENT])
        if self.created:
            for line in self.created:
                self.stdout.write(f"  created {line}")
            self.stdout.write(self.style.SUCCESS(f"Demo data ready: {len(self.created)} new records."))
        else:
            self.stdout.write(self.style.SUCCESS("Demo data already present: nothing to create."))

    # --- academic structure ----------------------------------------------------------------

    def _get_or_create(self, model, label, defaults=None, **lookup):
        obj, created = model.objects.get_or_create(defaults=defaults or {}, **lookup)
        if created:
            self.created.append(label)
        return obj

    def _structure(self):
        batch = Batch.objects.filter(name__in=(BATCH_NAME, *OLD_BATCH_NAMES)).order_by("pk").first()
        if batch is None:
            batch = self._get_or_create(Batch, f"batch {BATCH_NAME}", name=BATCH_NAME)
        elif batch.name != BATCH_NAME:
            batch.name = BATCH_NAME
            batch.save(update_fields=["name"])
            self.created.append(f"batch name corrected to {BATCH_NAME}")
        semester = self._get_or_create(Semester, "Semester 4", number=4)
        sections = {name: self._get_or_create(Section, f"section {name}", name=name) for name in STUDENTS}
        name, start, end = TERM
        term = AcademicTerm.objects.filter(name=name).first() or self._get_or_create(
            AcademicTerm, f"term {name}", name=name, defaults={"start_date": start, "end_date": end})
        if not AcademicTerm.objects.filter(is_current=True).exists():
            academic_services.set_current_term(term)
            self.created.append(f"current term {name}")
        categories = {}
        for position, category in enumerate(CATEGORIES, start=1):
            categories[category] = self._get_or_create(
                ComplaintCategory, f"category {category}", name=category, defaults={"position": position})
        return {"batch": batch, "semester": semester, "sections": sections, "categories": categories}

    # --- people ----------------------------------------------------------------------------

    def _user(self, email, full_name, role):
        user = User.objects.filter(email=email).first()
        if user is None:
            if role == User.Role.SUPER_ADMIN:
                user = User.objects.create_superuser(email=email, full_name=full_name)
            else:
                user = User.objects.create_user(email=email, full_name=full_name, role=role)
            self.created.append(f"{user.get_role_display()} {email}")
        return user

    def _people(self, structure):
        admin = self._user(*ADMIN, User.Role.SUPER_ADMIN)
        advisors = {email: self._user(email, name, User.Role.BATCH_ADVISOR) for email, name in ADVISORS}
        batch, semester = structure["batch"], structure["semester"]
        assignments = [(ADVISORS[0][0], "DEMO-A"), (ADVISORS[0][0], "DEMO-B"), (ADVISORS[1][0], "DEMO-B")]
        for email, section in assignments:
            self._get_or_create(
                AdvisorAssignment, f"assignment {email} to {section}", defaults={"assigned_by": admin},
                advisor=advisors[email], batch=batch, semester=semester, section=structure["sections"][section])
        students = {}
        for section_name, rows in STUDENTS.items():
            for email, name in rows:
                user = self._user(email, "", User.Role.STUDENT)
                if not StudentProfile.objects.filter(user=user).exists():
                    account_services.register_student(user, full_name=name, batch=batch, semester=semester,
                                                      section=structure["sections"][section_name])
                    self.created.append(f"registration {email} in {section_name}")
                students[email] = user
        return {"admin": admin, "advisors": advisors, "students": students}

    def _demo_staff(self, structure, people):
        """DEMO_STAFF_EMAILS (DEC-327): the first is a Super Admin, the second a Batch Advisor of
        both demo cohorts. Created or updated; running again changes nothing."""
        listed = list(dict.fromkeys(identity.normalize_email(email) for email in settings.DEMO_STAFF_EMAILS))
        emails = identity.demo_staff_emails()
        if listed != emails:  # a skipped entry would silently shift who gets which role
            raise CommandError("DEMO_STAFF_EMAILS must contain valid, non-student email addresses.")
        roles = [(User.Role.SUPER_ADMIN, "Demo Staff Admin"), (User.Role.BATCH_ADVISOR, "Demo Staff Advisor")]
        for email, (role, name) in zip(emails, roles):
            user = self._user(email, name, role)
            if user.role != role:
                user.role = role
                user.save(update_fields=["role", "is_staff", "is_superuser"])
                self.created.append(f"role of {email} set to {user.get_role_display()}")
            if role == User.Role.BATCH_ADVISOR:
                for section_name, section in structure["sections"].items():
                    self._get_or_create(
                        AdvisorAssignment, f"assignment {email} to {section_name}",
                        defaults={"assigned_by": people["admin"]}, advisor=user, batch=structure["batch"],
                        semester=structure["semester"], section=section)

    # --- complaints --------------------------------------------------------------------------

    def _at(self, days_ago, minute):
        """A moment `days_ago` days before now, at a stable time of day (spread by `minute`)."""
        return self.now - timedelta(days=days_ago, hours=3, minutes=minute)

    def _complaints(self, structure, people):
        admin = people["admin"]
        demo_student_complaints = 0
        for index, (email, category, title, description, steps) in enumerate(COMPLAINTS):
            student = people["students"][email]
            if Complaint.objects.filter(student=student, title=title).exists():
                continue
            section = StudentProfile.objects.get(user=student).section.name
            advisor = people["advisors"][SECTION_ADVISOR[section]]
            first_step = steps[0][0] if steps else 0
            submitted_days_ago = max(first_step + 1, 21 - index)
            with mock.patch("django.utils.timezone.now", return_value=self._at(submitted_days_ago, index)):
                complaint = services.submit_complaint(student, category=structure["categories"][category],
                                                      title=title, description=description)
            for step, (days_ago, action, text) in enumerate(steps):
                with mock.patch("django.utils.timezone.now", return_value=self._at(days_ago, index * 3 - step)):
                    self._step(complaint, action, text, student=student, advisor=advisor, admin=admin)
            self.created.append(f"complaint {complaint.reference} ({title})")
            demo_student_complaints += email == DEMO_STUDENT
        return demo_student_complaints

    # --- Student Voice -----------------------------------------------------------------------

    def _voice(self, people):
        """Real submissions through voice.services. An existing one (same student and text) is left alone."""
        for index, (email, kind, text, days_ago, action, action_days_ago, reply) in enumerate(VOICE_SUBMISSIONS):
            student = people["students"][email]
            if Submission.objects.filter(student=student, text=text).exists():
                continue
            section = StudentProfile.objects.get(user=student).section.name
            advisor = people["advisors"][SECTION_ADVISOR[section]]
            with mock.patch("django.utils.timezone.now", return_value=self._at(days_ago, index)):
                submission = voice_services.submit(student, type=kind, text=text)
            if action:
                with mock.patch("django.utils.timezone.now", return_value=self._at(action_days_ago, index)):
                    if action == "answer":
                        voice_services.answer(advisor, submission, reply)
                    else:
                        voice_services.mark_reviewed(advisor, submission)
            self.created.append(f"Student Voice {kind} from {email}")

    def _step(self, complaint, action, text, *, student, advisor, admin):
        complaint = Complaint.objects.get(pk=complaint.pk)
        if action == "review":
            services.change_status(advisor, complaint, Complaint.Status.UNDER_REVIEW, text)
        elif action == "respond":
            services.respond(advisor, complaint, text)
        elif action == "admin_respond":
            services.respond(admin, complaint, text)
        elif action == "resolve":
            services.change_status(advisor, complaint, Complaint.Status.RESOLVED, text)
        elif action == "reject":
            services.change_status(advisor, complaint, Complaint.Status.REJECTED, text)
        elif action == "still":
            services.mark_still_not_resolved(student, complaint, text)
        elif action == "info":
            services.add_further_information(student, complaint, text)
        elif action == "cancel":
            services.request_cancellation(student, complaint, text)
        elif action == "owner":
            services.assign_responsible(admin, complaint, advisor)
        else:
            raise CommandError(f"Unknown demo step: {action}")

    def _mark_older_updates_read(self, student):
        """Leave the demo student's two newest notifications unread and mark the rest read, so
        Student Home shows both new and earlier updates. Only on the run that creates them."""
        unread = list(Notification.objects.filter(recipient=student, read_at__isnull=True).order_by("-created_at", "-id"))
        for notification in unread[2:]:
            notification_services.mark_read(student, notification.pk)
