<script lang="ts">
	import CsvImportPage from '$lib/components/CsvImportPage.svelte';
	import { downloadStudentTemplate, importStudents } from '$lib/features/admin/service';
	import { Routes } from '$lib/shared/constants/routes';

	// CSV Import (wireframe 4.3): Step 1 download template, Step 2 upload file,
	// Step 3 preview + confirm against POST /admin/students/import. The backend
	// creates NEW roster records; columns are
	// student_id, first_name, middle_name, last_name, email, program_code,
	// section, year_level.
</script>

<CsvImportPage
	title="Import Students from CSV"
	subtitle="Bulk-create new roster records · duplicates are skipped, errors reported per line"
	columnsHelp="student_id, first_name, middle_name, last_name, email, program_code, section, year_level"
	templateFilename="students_template.csv"
	errorsFilename="students_import_errors.csv"
	expectedHeaders={['student_id', 'first_name', 'middle_name', 'last_name', 'email', 'program_code', 'section', 'year_level']}
	endpointNote="POST /admin/students/import"
	templateNote="Server template when reachable, otherwise a matching static header."
	backLabel="Back to Students"
	backHref={Routes.ADMIN_STUDENTS}
	entityEvent="students"
	downloadTemplate={downloadStudentTemplate}
	importFile={importStudents}
/>
