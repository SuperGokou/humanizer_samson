"""Offline integration tests: real files, CLI, and persisted catalog."""
import json, pathlib, subprocess, sys, tempfile, unittest, hashlib
CLI=pathlib.Path(__file__).resolve().parents[1]/'corpus/scripts/manage.py'
XML='''<article xml:lang="en"><front><journal-meta><journal-title-group><journal-title>Test Journal</journal-title></journal-title-group></journal-meta><article-meta><article-id pub-id-type="doi">10.1234/example</article-id><title-group><article-title>Testing financial models</article-title></title-group><pub-date pub-type="epub"><year>2021</year></pub-date><permissions><license><license-p>https://creativecommons.org/licenses/by/4.0/</license-p></license></permissions></article-meta></front><body><sec><title>Results</title><p>We observed a stable association. The estimate was 3.14 with p &lt; 0.05.</p><p>The model uses <inline-formula><tex-math>x^2+y^2</tex-math></inline-formula> without changing the result.</p></sec></body><back><ref-list><ref><mixed-citation>REFERENCE MUST NOT ENTER BODY.</mixed-citation></ref></ref-list></back></article>'''
class CorpusTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=pathlib.Path(self.tmp.name)/'corpus';self.root.mkdir()
 def runcli(self,*args,ok=True):
  p=subprocess.run([sys.executable,str(CLI),'--root',str(self.root),*map(str,args)],capture_output=True,text=True)
  if ok:self.assertEqual(p.returncode,0,p.stderr+p.stdout)
  else:self.assertNotEqual(p.returncode,0)
  return p
 def rows(self):return json.loads((self.root/'catalog.json').read_text())
 def put(self,rows,name='input.json'):
  p=pathlib.Path(self.tmp.name)/name;p.write_text(json.dumps(rows));return p
 def xml(self,name='paper.xml'):
  p=pathlib.Path(self.tmp.name)/name;p.write_text(XML);return p
 def test_repeated_import_normalizes_doi_and_does_not_grow_history(self):
  a=self.put([{'doi':'https://doi.org/10.1234/EXAMPLE','title':'Testing','year':2021,'category':'Finance'}]);self.runcli('import',a)
  first=self.rows();history=(self.root/'history.jsonl').read_text();self.runcli('import',a)
  self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows(),first);self.assertEqual((self.root/'history.jsonl').read_text(),history)
  self.assertEqual(first[0]['doi'],'https://doi.org/10.1234/example')
 def test_attach_fulltext_preserves_human_fields_and_exclusions(self):
  p=self.put([{'doi':'10.1234/example','title':'Human corrected title','year':2021,'category':'Finance'}]);self.runcli('import',p)
  self.runcli('review','10.1234/example','--decision','hold','--note','Do not use pending review')
  self.runcli('import',self.xml(),'--category','Science')
  row=self.rows()[0];self.assertEqual(row['title'],'Human corrected title');self.assertEqual(row['category'],'Finance');self.assertEqual(row['manual_review']['decision'],'hold');self.assertTrue((self.root/row['local_file']).exists())
  self.runcli('organize');self.assertEqual(self.rows()[0]['pipeline_status'],'held')
 def test_same_file_with_conflicting_doi_is_not_a_second_paper(self):
  f=self.xml();self.runcli('import',f,'--category','Finance')
  side=f.with_suffix('.json');side.write_text(json.dumps({'doi':'10.9999/wrong','category':'Finance'}))
  before=self.rows();self.runcli('import',f,ok=False);self.assertEqual(self.rows(),before)
 def test_xml_retains_formula_context_and_excludes_references(self):
  self.runcli('import',self.xml(),'--category','Finance');self.runcli('organize');r=self.rows()[0]
  doc=json.loads((self.root/r['processed_file']).read_text());text=' '.join(p['text'] for p in doc['paragraphs'])
  self.assertIn('3.14',text);self.assertNotIn('REFERENCE MUST',text);self.assertIn('[FORMULA_1]',text);self.assertIn('x^2+y^2',doc['formulas'][0]['source'])
  self.assertEqual(doc['paragraphs'][0]['section'],'Results');self.assertEqual(r['pipeline_status'],'review_required')
  before=(self.root/r['processed_file']).stat().st_mtime_ns;self.runcli('organize');self.assertEqual((self.root/r['processed_file']).stat().st_mtime_ns,before)
 def test_newer_year_does_not_enter_ready_set_even_if_approved(self):
  f=self.xml();f.write_text(XML.replace('2021','2023'));self.runcli('import',f,'--category','Finance')
  self.runcli('review','10.1234/example','--decision','approve','--note','Article type and style checked');self.runcli('organize')
  self.assertEqual(self.rows()[0]['pipeline_status'],'out_of_scope')
 def test_restricted_license_blocks_approval_from_ready_set(self):
  f=self.xml();f.write_text(XML.replace('/licenses/by/','/licenses/by-nc/'));self.runcli('import',f,'--category','Finance')
  self.runcli('review','10.1234/example','--decision','approve','--note','Quality approved only');self.runcli('organize')
  self.assertEqual(self.rows()[0]['pipeline_status'],'license_review')
 def test_failed_batch_does_not_partially_write_catalog(self):
  p=self.put([{'doi':'10.1234/example','title':'First'},{'doi':'bad doi','title':'Second'}]);self.runcli('import',p,ok=False)
  self.assertFalse((self.root/'catalog.json').exists())
 def test_broken_xml_can_be_replaced_and_reprocessed(self):
  f=self.xml();self.runcli('import',f,'--category','Finance');r=self.rows()[0];p=self.root/r['local_file'];original=p.read_bytes();p.write_bytes(b'<bad>')
  self.runcli('organize');self.assertEqual(self.rows()[0]['pipeline_status'],'integrity_error')
  p.write_bytes(original);self.runcli('organize');self.assertEqual(self.rows()[0]['pipeline_status'],'review_required')
 def test_report_accepts_non_1000_count_and_preserves_user_readme(self):
  self.runcli('import',self.put([{'doi':'10.1234/example','title':'Test','category':'Finance','year':2021}]))
  (self.root/'README.md').write_text('USER DOCUMENTATION');self.runcli('report')
  self.assertEqual((self.root/'README.md').read_text(),'USER DOCUMENTATION')
  summary=json.loads((self.root/'reports/summary.json').read_text());self.assertEqual(summary['total'],1)
 def test_filename_without_doi_is_tracked_and_not_automatically_ready(self):
  f=self.xml();f.write_text(XML.replace('<article-id pub-id-type="doi">10.1234/example</article-id>',''));self.runcli('import',f,'--category','Finance');self.runcli('organize')
  self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['pipeline_status'],'metadata_review')
 def test_unprocessed_fulltext_cannot_be_ready(self):
  self.runcli('import',self.xml(),'--category','Finance');self.runcli('review','10.1234/example','--decision','approve','--note','Reviewed')
  self.assertNotEqual(self.rows()[0]['pipeline_status'],'ready')
 def test_unknown_category_is_completed_by_later_import(self):
  self.runcli('import',self.put([{'doi':'10.1234/example','title':'Testing'}]))
  self.runcli('import',self.xml(),'--category','Finance');self.assertEqual(self.rows()[0]['category'],'Finance')
 def test_retracted_article_cannot_enter_ready_set(self):
  f=self.xml();f.with_suffix('.json').write_text(json.dumps({'is_retracted':True}));self.runcli('import',f,'--category','Finance')
  self.runcli('organize');self.runcli('review','10.1234/example','--decision','approve','--note','Quality checked')
  self.assertEqual(self.rows()[0]['pipeline_status'],'retracted')
 def test_unknown_year_stays_in_metadata_review(self):
  f=self.xml();f.write_text(XML.replace('<year>2021</year>',''));self.runcli('import',f,'--category','Finance');self.runcli('organize')
  self.assertEqual(self.rows()[0]['pipeline_status'],'metadata_review')
 def test_formula_only_math_does_not_lose_its_xml_source(self):
  f=self.xml();f.write_text(XML.replace('<p>We observed', '<disp-formula><tex-math>a=b+c</tex-math></disp-formula><p>We observed'))
  self.runcli('import',f,'--category','Mathematics');self.runcli('organize');r=self.rows()[0];doc=json.loads((self.root/r['processed_file']).read_text())
  self.assertEqual(doc['paragraphs'][0]['kind'],'formula');self.assertIn('a=b+c',doc['formulas'][0]['source'])
 def test_batch_rejects_invalid_doi_with_specific_error(self):
  result=self.runcli('import',self.put([{'doi':'10.1234/valid'},{'doi':'invalid'}]),ok=False)
  self.assertIn('Invalid DOI',result.stderr);self.assertFalse((self.root/'catalog.json').exists())
 def test_xml_processing_instructions_do_not_drop_prose(self):
  f=self.xml();f.write_text(XML.replace('We observed','<?journal marker?><!-- ignored -->We observed'))
  self.runcli('import',f,'--category','Finance');self.runcli('organize');r=self.rows()[0]
  self.assertNotIn('processing_error',r)
  doc=json.loads((self.root/r['processed_file']).read_text());self.assertIn('We observed',doc['paragraphs'][0]['text']);self.assertNotIn('ignored',doc['paragraphs'][0]['text'])
 def test_exported_sentence_candidates_keep_provenance_and_exclude_held(self):
  self.runcli('import',self.xml(),'--category','Finance');self.runcli('organize')
  path=self.root/'index/candidate_sentences.jsonl';self.assertTrue(path.exists())
  chunks=[json.loads(x) for x in path.read_text().splitlines()];self.assertGreater(len(chunks),0)
  self.assertEqual(chunks[0]['doi'],'https://doi.org/10.1234/example');self.assertTrue(chunks[0]['paragraph_id']);self.assertEqual(chunks[0]['section'],'Results')
  self.runcli('review','10.1234/example','--decision','hold','--note','Questionable article type');self.assertEqual(path.read_text(),'')
 def test_new_version_of_fulltext_keeps_original_asset(self):
  f=self.xml();self.runcli('import',f,'--category','Finance');first=self.rows()[0]['local_file'];f.write_text(XML.replace('3.14','3.15'))
  self.runcli('import',f,'--category','Finance');row=self.rows()[0]
  self.assertNotEqual(first,row['local_file']);self.assertTrue((self.root/first).exists());self.assertEqual(row['asset_versions'][0]['local_file'],first)
 def test_report_does_not_reset_review(self):
  self.runcli('import',self.xml(),'--category','Finance');self.runcli('review','10.1234/example','--decision','hold','--note','Preserve this')
  before=self.rows()[0]['manual_review'];self.runcli('report');self.assertEqual(self.rows()[0]['manual_review'],before)
 def test_imported_csv_can_attach_local_file(self):
  self.xml();p=pathlib.Path(self.tmp.name)/'papers.csv';p.write_text('doi,category,local_file\n10.1234/example,Finance,paper.xml\n')
  self.runcli('import',p);self.assertTrue((self.root/self.rows()[0]['local_file']).exists())
 def test_directory_import_reads_sidecar_once(self):
  folder=pathlib.Path(self.tmp.name)/'inbox';folder.mkdir();f=folder/'paper.xml';f.write_text(XML);f.with_suffix('.json').write_text(json.dumps({'category':'Finance'}))
  self.runcli('import',folder);self.assertEqual(len(self.rows()),1);self.assertEqual(self.rows()[0]['category'],'Finance')
 def test_import_records_original_source_path(self):
  p=self.put([{'doi':'10.1234/example','title':'Testing'}]);self.runcli('import',p)
  self.assertIn(str(p.resolve()),self.rows()[0].get('import_sources',[]))
 def test_csv_attachment_fills_metadata_from_xml(self):
  self.xml();p=pathlib.Path(self.tmp.name)/'papers.csv';p.write_text('doi,category,local_file\n10.1234/example,Finance,paper.xml\n')
  self.runcli('import',p);r=self.rows()[0];self.assertEqual(r.get('title'),'Testing financial models');self.assertEqual(r.get('year'),2021)
 def test_category_hint_fills_unclassified_record(self):
  p=self.put([{'doi':'10.1234/example','category':'Unclassified'}]);self.runcli('import',p,'--category','Finance')
  self.assertEqual(self.rows()[0]['category'],'Finance')
 def test_new_fulltext_version_requires_new_review(self):
  f=self.xml();self.runcli('import',f,'--category','Finance');self.runcli('organize');self.runcli('review','10.1234/example','--decision','approve','--note','Checked first version')
  self.assertEqual(self.rows()[0]['pipeline_status'],'ready')
  f.write_text(XML.replace('3.14','3.15'));self.runcli('import',f,'--category','Finance');self.assertNotEqual(self.rows()[0]['pipeline_status'],'ready')
  self.runcli('organize');self.assertEqual(self.rows()[0]['pipeline_status'],'review_required')
if __name__=='__main__':unittest.main()
