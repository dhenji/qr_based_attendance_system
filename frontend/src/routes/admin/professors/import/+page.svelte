<script lang="ts">
	import CsvImportPage from '$lib/components/CsvImportPage.svelte';
	import { downloadProfessorTemplate, importProfessors } from '$lib/features/admin/service';
	import { Routes } from '$lib/shared/constants/routes';

	// CSV Import: Step 1 download template, Step 2 upload file,
	// Step 3 preview + confirm against POST /admin/professors/import. The
	// backend creates NEW roster records; columns are
	// first_name, middle_name, last_name, email, department
	// (first/last/email required). There is no professor template route
	// server-side, so the template falls back to a static header in backend
	// column order.
</script>

<CsvImportPage
	title="Import Professors from CSV"
	subtitle="Bulk-create new roster records · duplicates are skipped, errors reported per line"
	columnsHelp="first_name, middle_name, last_name, email, department"
	templateFilename="professors_template.csv"
	errorsFilename="professors_import_errors.csv"
	expectedHeaders={['first_name', 'middle_name', 'last_name', 'email', 'department']}
	endpointNote="POST /admin/professors/import"
	templateNote="Static header — no server template route exists for professors."
	backLabel="Back to Professors"
	backHref={Routes.ADMIN_PROFESSORS}
	entityEvent="professors"
	downloadTemplate={downloadProfessorTemplate}
	importFile={importProfessors}
/>
