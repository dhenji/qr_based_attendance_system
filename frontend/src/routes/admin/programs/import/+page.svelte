<script lang="ts">
	import CsvImportPage from '$lib/components/CsvImportPage.svelte';
	import { downloadProgramTemplate, importPrograms } from '$lib/features/admin/programs/service';
	import { Routes } from '$lib/shared/constants/routes';

	// CSV Import (wireframe 4.3 pattern): Step 1 download template, Step 2
	// upload file, Step 3 preview + confirm against POST
	// /admin/programs/import. The backend creates NEW program records;
	// columns are code, name, description, total_years. Year levels are
	// added later on the program detail page, matching single-create.
</script>

<CsvImportPage
	title="Import Programs from CSV"
	subtitle="Bulk-create new programs · duplicates are skipped, errors reported per line"
	columnsHelp="code, name, description, total_years"
	templateFilename="programs_template.csv"
	errorsFilename="programs_import_errors.csv"
	expectedHeaders={['code', 'name', 'description', 'total_years']}
	endpointNote="POST /admin/programs/import"
	templateNote="Server template when reachable, otherwise a matching static header. Year levels are added next, on each program detail page."
	backLabel="Back to Programs"
	backHref={Routes.ADMIN_PROGRAMS}
	entityEvent="programs"
	downloadTemplate={downloadProgramTemplate}
	importFile={importPrograms}
/>
