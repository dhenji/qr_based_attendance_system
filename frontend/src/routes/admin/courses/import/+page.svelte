<script lang="ts">
	import CsvImportPage from '$lib/components/CsvImportPage.svelte';
	import { downloadCourseTemplate, importCourses } from '$lib/features/admin/courses/service';
	import { Routes } from '$lib/shared/constants/routes';

	// CSV Import (wireframe 4.3 pattern): Step 1 download template, Step 2
	// upload file, Step 3 preview + confirm against POST
	// /admin/courses/import. The backend creates NEW standalone course
	// templates (D44); columns are course_code, course_name, units,
	// session_duration_hours. Program, schedule, and classroom attach later
	// via offerings.
</script>

<CsvImportPage
	title="Import Courses from CSV"
	subtitle="Bulk-create new course templates · duplicates are skipped, errors reported per line"
	columnsHelp="course_code, course_name, units, session_duration_hours"
	templateFilename="courses_template.csv"
	errorsFilename="courses_import_errors.csv"
	expectedHeaders={['course_code', 'course_name', 'units', 'session_duration_hours']}
	endpointNote="POST /admin/courses/import"
	templateNote="Server template when reachable, otherwise a matching static header. Program, schedule, and classroom attach later via offerings."
	backLabel="Back to Courses"
	backHref={Routes.ADMIN_COURSES}
	entityEvent="courses"
	downloadTemplate={downloadCourseTemplate}
	importFile={importCourses}
/>
