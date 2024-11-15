#!/usr/bin/env python3
#
# A simple, self-contained report generator for penetration testing reports.
#
# Lauritz Holtmann, (c) 2022 - 2023
#

import io
import os
import re
import sys
import yaml
import pdfkit
import argparse
import datetime
import markdown
import xlsxwriter
import matplotlib.pyplot as plt
from cvss import CVSS3
from datetime import date
from string import Template

# Constants
content_dir = "content/"
findings_dir = "findings/"
output_dir = "output/"
boilerplate_dir = "boilerplate/"
page_break = '\n\n<div style = "display:block; clear:both; page-break-after:always;"></div>\n\n'

# Global Variables
config = {}
findings = []
report_md = ""
report_html = ""
findings_list = ""
cover_location = ""
generated_piechart = ""
total_findings = critical_findings = high_findings = medium_findings = low_findings = none_findings = 0

# Set Base-URL to current working directory 
# Makes including images to report more easy by simply referencing images/test.png
report_md += "<base href=\"file://{}/\">\n\n".format(os.getcwd())


def init():
	"""Initialize the report generator, load config from config.yaml"""
	global config
	# Parse Config
	with open('config.yaml') as f:
		config = yaml.load(f, Loader=yaml.FullLoader)
		print("Config options: {}".format(config))
		f.close()

def generate_report():
	"""Generate the PDF report"""
	global report_html
	# Generate Markdown Report
	generate_markdown_report()
	# Generate PDF Report
	generate_pdf_report(report_html)

def generate_markdown_report():
	"""Generate the Markdown report from the Markdown template and findings"""
	global config, content_dir, cover_location, findings, findings_dir, report_md, report_html, total_findings, critical_findings, high_findings, medium_findings, low_findings, none_findings

	# Glue: Collect files and build Markdown report
	with open(content_dir + 'introduction.md') as f:
		report_md += f.read()
		report_md += page_break
		f.close()

	with open(content_dir + 'scope.md') as f:
		report_md += f.read()
		report_md += page_break
		f.close()

	with open(content_dir + 'technical-details.md') as f:
		report_md += f.read()
		report_md += page_break
		f.close()

	# Insert Placeholders
	report_md = report_md.format(
		title = config["title"], 
		author = config["author"], 
		customer = config["customer"],
		critical_findings = "{critical_findings}",
		high_findings = "{high_findings}",
		medium_findings = "{medium_findings}",
		low_findings = "{low_findings}",
		piechart = "{piechart}",
		findings_list = "{findings_list}"
	)

	# Process Findings
	process_findings()

	# Determine Statistics and Render Pie Chart
	print("Generating Pie Chart...")

	## Data for the pie chart
	# Optional: Include informational findnigs
	#labels = ['Critical', 'High', 'Medium', 'Low', 'None']
	#sizes = [critical_findings, high_findings, medium_findings, low_findings, none_findings]
	#colors = ['violet', 'red', 'orange', 'yellow', 'green']
	labels = ['Critical', 'High', 'Medium', 'Low']
	sizes = [critical_findings, high_findings, medium_findings, low_findings]
	colors = ['violet', 'red', 'orange', 'yellow']

	## Set font size and padding for legend
	plt.rcParams['font.size'] = 12
	plt.rcParams['legend.fontsize'] = 12
	plt.rcParams['font.family'] = 'sans-serif'
	plt.rcParams['font.sans-serif'] = ['avenir']
	plt.rcParams["figure.autolayout"] = True

	## Create the pie chart as an SVG in memory
	fig, ax = plt.subplots()
	ax.pie(sizes, labels=None, colors=colors, autopct=lambda pct: f"{pct:.1f}%" if pct > 0 else '')
	ax.axis('equal')
	### Set legend
	plt.subplots_adjust(left=0.1, right=0.5)
	ax.legend(labels, loc='center left', bbox_to_anchor=(1, 0.5), title='Distribution of Findings by Severity')
	leg = ax.get_legend()
	leg._legend_box.align = "left"
	svg_io = io.BytesIO()
	plt.savefig(svg_io, format='svg')
	svg_io.seek(0)
	generated_piechart = svg_io.getvalue().decode('utf-8')

	## Create the detailed table of findings
	generated_table_of_findings = ""
	for counter,finding in enumerate(findings):
		# Fill Template
		generated_table_of_findings += "* <b style='display:inline-block;width:100px'>{}</b> #PEN{}{:04d}:\t{} ([CWE-{}](https://cwe.mitre.org/data/definitions/{}.html))\n".format(finding["cvss_severity"], date.today().year, counter+1, finding["title"], finding["CWE-ID"], finding["CWE-ID"])

	# Insert Placeholders
	report_md = report_md.format(
		critical_findings = critical_findings,
		high_findings = high_findings,
		medium_findings = medium_findings,
		low_findings = low_findings,
		piechart = "{piechart}",
		findings_list = generated_table_of_findings
	)

	# Append processed findings to report
	for counter,finding in enumerate(findings):
		print("Appending finding {}...".format(finding["title"]))
		# Fill Template
		report_md += finding_markdown(finding, "#PEN{}{:04d}".format(date.today().year, counter+1))

	# Append Conclusion and Appendix
	with open(content_dir + 'conclusion.md') as f:
		report_md += f.read() 
		report_md += page_break
		f.close()

	with open(content_dir + 'appendix.md') as f:
		report_md += f.read() 
		report_md += page_break
		f.close()

	# Render Markdown: Convert to main report to HTML
	print("Render Markdown to HTML...")
	report_html = markdown.markdown(report_md, extensions=['fenced_code', 'codehilite', 'tables'])

	cover_location = "temp/cover_processed.html"
	with open(boilerplate_dir + 'cover.html') as f:
		cover_processed = Template(f.read()).safe_substitute(title=config["title"], author=config["author"], date=datetime.datetime.now().strftime("%Y-%m-%d"), customer=config["customer"])
		f.close()

	with open(cover_location, 'w') as f:
		f.write(cover_processed)
		f.close()

	# Insert inlined SVG
	report_html = report_html.replace("{piechart}", generated_piechart)

def finding_markdown(finding, finding_id = "TBD"):
	"""Generate Markdown for a single finding"""
	temp = """
### {}: {}

---

| Asset         | CWE                                                      | Severity (CVSS v3.1 Base Score) | CVSS v3.1 Vector                                                                             |
|---------------|----------------------------------------------------------|---------------------------------|----------------------------------------------------------------------------------------------|
| {} | [{}]({}) | {} ({})                      | *{}* |

---

{}

	""".format(
		finding_id,
		finding["title"],
		finding["asset"],
		finding["CWE-ID"],
		finding["CWE-Link"],
		finding["cvss_severity"],
		finding["cvss_score"],
		finding["cvss_vector"],
		finding["description"]
	)
	return temp + page_break

def process_findings():
	"""Process all findings and generate statistics"""
	global config, findings, findings_dir, total_findings, critical_findings, high_findings, medium_findings, low_findings, none_findings

	# Iterate over finding MD files, preprocess
	for file in os.listdir(findings_dir):
		if file.endswith(".md"):
			filename = os.fsdecode(file)
			with open(findings_dir + filename) as f:
				print("Processing finding {}...".format(filename))
				finding = {}

				# Map finding description from MD file
				finding["description"] = f.read()
				f.close()

				# Parse Properties from Header Section
				re_search = re.search(r"<!--[\r\n]([\s\S]*)[\r\n]-->", finding["description"])
				properties_yaml = re_search.group(1)
				properties = yaml.load(properties_yaml, Loader=yaml.FullLoader)
				# Cleanup: Remove properties
				finding["description"] = finding["description"].replace(re_search.group(0), "")

				# Map Properties
				finding["title"] = properties["title"]
				finding["asset"] = properties["asset"]
				finding["CWE-ID"] = properties["CWE-ID"]
				finding["CWE-Link"] = properties["CWE-Link"]
				if "finding_id" in properties:
					finding["finding_id"] = properties["finding_id"]

				# calculate CVSS score and severity
				cvss_vector = "CVSS:3.1/AV:{}/AC:{}/PR:{}/UI:{}/S:{}/C:{}/I:{}/A:{}".format(properties["cvss"]["AV"], properties["cvss"]["AC"], properties["cvss"]["PR"], properties["cvss"]["UI"], properties["cvss"]["S"], properties["cvss"]["C"], properties["cvss"]["I"],properties["cvss"]["A"])
				c = CVSS3(cvss_vector)
				finding["cvss_vector"] = c.clean_vector()
				finding["cvss_score"] = c.scores()[0]
				finding["cvss_severity"] = c.severities()[0]

				findings.append(finding)
		else:
			print("File {} does not have correct file type .md".format(file))

	# Sort findings, CVSS Score descending
	def useScore(elem):
		return elem["cvss_score"]
	findings.sort(key=useScore,reverse=True)

	total_findings = len(findings)
	critical_findings = len([finding for finding in findings if finding["cvss_severity"] == "Critical"])
	high_findings = len([finding for finding in findings if finding["cvss_severity"] == "High"])
	medium_findings = len([finding for finding in findings if finding["cvss_severity"] == "Medium"])
	low_findings = len([finding for finding in findings if finding["cvss_severity"] == "Low"])
	none_findings = len([finding for finding in findings if finding["cvss_severity"] == "None"])


def generate_excel_report():
	"""Generate Excel Report"""
	global config, findings, output_dir
	# Write findings to Excel file
	print("Generating Excel file...")
	excel_report = xlsxwriter.Workbook(output_dir + 'report.xlsx')
	excel_report_sheet = excel_report.add_worksheet("Findings")
	bold = excel_report.add_format({'bold': True})
	table_header = excel_report.add_format({'bold': True, 'bg_color': '#c8c8cf'})

	# Title
	excel_report_sheet.write(0, 0, "Pentest Report: {}".format(config["title"]), bold)
	excel_report_sheet.write(1, 0, "Author: {}".format(config["author"]))
	excel_report_sheet.write(2, 0, "Date: {}".format(datetime.datetime.now().strftime("%Y-%m-%d")))

	# Table Header
	excel_report_sheet.write(4, 0, "Finding-ID", table_header)
	excel_report_sheet.write(4, 1, "Severity", table_header)
	excel_report_sheet.write(4, 2, "Asset", table_header)
	excel_report_sheet.write(4, 3, "Title", table_header)

	# Findings
	row = 5
	col = 0 
	for counter,finding in enumerate(findings):
		excel_report_sheet.write(row, col, "#PEN{}{:04d}".format(date.today().year,counter+1), bold)
		excel_report_sheet.write(row, col + 1, "{} ({})".format(finding["cvss_severity"], finding["cvss_score"]))
		excel_report_sheet.write(row, col + 2, finding["asset"])
		excel_report_sheet.write(row, col + 3, finding["title"])
		row += 1

	excel_report.close()


def generate_pdf_report(report_html, mode = "report", filename = "finding.md"):
	"""Generate PDF Report from HTML"""
	global boilerplate_dir, cover_location, output_dir
	# Generate PDF
	toc = {
		'xsl-style-sheet': boilerplate_dir + 'toc.xsl'
	}

	options = {
		'--header-html': boilerplate_dir + 'header.html',
		'--footer-html': boilerplate_dir + 'footer.html',
		#'footer-right': '[page] of [topage]',
		'footer-right': '[page]',
		'footer-font-name': 'avenir next',
		'footer-font-size': '10',
		'margin-bottom': '1.25cm', 
		'margin-top': '2.5cm',
		'header-spacing': '-5',
		'encoding': "UTF-8",
		'page-size': 'A4',
		"enable-local-file-access": None
	}

	css = boilerplate_dir + "report.css"

	print("Generating PDF...")
	if mode == "report":
		pdfkit.from_string(report_html, output_dir+'report.pdf', options=options, css=css, toc=toc, cover=cover_location, cover_first=True)
	elif mode == "findings":
		pdfkit.from_string(report_html, output_dir+filename, options=options, css=css)

def all():
	"""Generate all reports"""
	generate_report()
	generate_excel_report()


def print_findings():
	global config, findings, findings_dir, total_findings, critical_findings, high_findings, medium_findings, low_findings, none_findings

	print("Processed {} findings:".format(total_findings))
	print("Critical: {}".format(critical_findings))
	print("High: {}".format(high_findings))
	print("Medium: {}".format(medium_findings))
	print("Low: {}".format(low_findings))
	print("None: {}".format(none_findings))

	print("Findings:")
	for finding in findings:
		print("++++++++++++")
		print("Title: {}".format(finding["title"]))
		print("Asset: {}".format(finding["asset"]))
		print("Severity: {}".format(finding["cvss_severity"]))
		print("CVSS Score: {}".format(finding["cvss_score"]))
		print("")

def generate_findings_reports():
	"""Generate separate report files for all findings"""
	global config, findings

	for counter,finding in enumerate(findings):
		if "finding_id" in finding:
			finding_id = finding["finding_id"]
		else:
			finding_id = "PEN{}{:04d}".format(date.today().year,counter+1)
		print("Generating report for finding #{}...".format(finding_id))
		finding_markdown_temp =  "<base href=\"file://{}/\">\n\n".format(os.getcwd()) + finding_markdown(finding, finding_id)
		finding_html = markdown.markdown(finding_markdown_temp, extensions=['fenced_code', 'codehilite', 'tables'])
		generate_pdf_report(finding_html, mode = "findings", filename = "finding_{}.pdf".format(finding_id))

################################################

if __name__ == '__main__':
	init()

	# Parse arguments
	parser = argparse.ArgumentParser(description='Render a pentest report.')
	parser.add_argument('--all', default=False, action='store_true', help='Generate all reports from scratch.')
	parser.add_argument('--view_findings', default=False, action='store_true', help='Print all findings.')
	parser.add_argument('--findings_only', default=False, action='store_true', help='Generate separate report files for all findings.')
	if len(sys.argv) == 1:
		parser.print_help(sys.stderr)
		sys.exit(1)
	args = parser.parse_args()

	if args.all:
		all()
	
	if args.view_findings:
		process_findings()
		print_findings()

	if args.findings_only:
		process_findings()
		generate_findings_reports()