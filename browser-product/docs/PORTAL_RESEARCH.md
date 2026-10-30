# Portal research shortlist — browser teammate

**Last desk review:** 31 Oct 2026. **Operational status:** no live authenticated portal walkthrough has been completed. **Day-1 Mumbai VM reachability is mandatory and not yet done; run `scripts/portal_reachability.py` inside the deployed worker per `docs/DEPLOY_MUMBAI.md`.** Unknown fields, upload limits, terms or selectors MUST be observed manually with authorised accounts; never fabricate them. The four-hour discovery spike in the work-split document is still open.

| Candidate | Official source | Known from sources | Actual form fields / document limits | Login and blockers | Demo recommendation | Verified end-to-end runs |
|---|---|---|---|---|---|---|
| National Scholarship Portal (NSP) | https://scholarships.gov.in/home | Academic year 2026–27, student/institute roles, mandatory OTR | **Not verified**; scheme-specific | OTR, Aadhaar/EID, NSP OTR app + Aadhaar Face RD, OTP; account and authorization required | Research/assisted mode only; no autonomous face-auth; demo fallback mock | **0** |
| Tamil Nadu e-Sevai services | https://tnesevai.tn.gov.in/Pages/EsevaiServiceListInstitution.aspx | Catalogue includes multiple scholarship-related services | **Not verified** | May be institution / service-center mediated, login and CAPTCHA vary | Manual walkthrough candidate | **0** |
| TN BC/MBC welfare scholarships | https://bcmbcmw.tn.gov.in/welfschemes.htm | Department lists education support and associated workflows | **Not verified** | Institution or department-specific restrictions unknown | Manual research candidate | **0** |
| MyScheme (scheme discovery, not application form) | https://www.myscheme.gov.in/ | Official scheme discovery entrypoint | Not an application automation target | Scheme links and criteria; may handoff to another portal | Citation and discovery only | N/A |
| Bundled fictional Student Aid Service Portal | http://127.0.0.1:8100/mock/ | Controlled complete synthetic application flow | Student name, course, family income, state, category, PDF <=1 MB **mock limit only** | Test OTP, manual arithmetic challenge, deliberate chaos | **Deterministic hackathon demonstration** | See TEST_REPORT.md |

## Four-hour manual research checklist

1. Record legal portal URL, consent/terms, browser-agent permissions, applicant vs institute access, and whether authentic test accounts are available.
2. Walk one **authorised** path by hand. Capture entry page, sign-in sequence, required OTR, genuine OTP or CAPTCHA, face-auth/device challenge, fields, upload formats/dimensions/file-size limits, final review and receipt.
3. Do not submit real applications without a qualifying citizen's explicit authorization. No automated CAPTCHA solving, Aadhaar face-auth simulation or scraping private account data.
4. Record redirects, session expiry symptoms, navigation quirks, DOM label/ARIA accessibility and field evidence. Keep screenshots redacted and access-controlled.
5. Assign each candidate a green/yellow/red feasibility status. Pick only the paths reliably reproducible from the Mumbai host and test **five complete runs each** using authorized accounts where possible.
6. If blocked, use mock end-to-end and demonstrate real portal research, with an explicit disclosure that no real application was submitted.

## Reference materials

- [NSP student announcements](https://scholarships.gov.in/student-announcements); [NSP OTR](https://scholarships.gov.in/otrapplication/).
- [Playwright locators](https://playwright.dev/python/docs/locators) and [ARIA snapshots](https://playwright.dev/python/docs/aria-snapshots).
- [UIDAI face authentication](https://uidai.gov.in/images/240826_UIDAI_Unlocking_face_authentication_playbook_Digital_version.pdf).
- [OWASP ASVS](https://asvs.owasp.org/); [India DPDP Act](https://www.indiacode.nic.in/indiacode/handle/123456789/22037?view_type=browse); [CERT-In directions](https://cert-in.org.in/PDF/CERT-In_Directions_70B_28.04.2022.pdf).

**Important:** Official portals are *references*, not integrated, supported or endorsed by this codebase.
