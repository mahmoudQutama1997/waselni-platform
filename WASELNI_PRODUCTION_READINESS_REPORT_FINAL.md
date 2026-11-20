# تقرير جاهزية WASELNI للإنتاج — متابعة المرحلة الأخيرة

## الخلاصة

**التصنيف الحالي: يمنع الاعتماد.** أُضيفت محليًا استعادة الحساب عبر البريد واختبارات إبطال الجلسة، لكن مزود البريد غير مضبوط/متحقق في Render. النسخ الاحتياطي والاستعادة المعزولة ومناطق الخدمة والمجدول التلقائي والتحقق الفعلي من ImageKit وRedis ما زالت غير منجزة أو متعذرة دون إعداد خارجي. لم يحدث Deploy أو تطبيق Migration على إنتاج؛ نشر الكود لا يزيل هذه الموانع.

## البنود السبعة المانعة — السبب والأولوية والتحقق

### P0 — حماية تسجيل الدخول من المحاولات المتكررة

- **السبب السابق:** مسار `POST /api/auth/token/` كان يستخدم `TokenObtainPairView` مباشرة دون throttle.
- **الملفات:** `backend/config/urls.py`، `backend/config/settings.py`، `backend/core/auth_views.py`، `backend/core/throttles.py`.
- **الإصلاح المحلي:** أضيف حد 5 محاولات في الدقيقة حسب عنوان العميل، مع استخدام Redis cache عندما يكون `REDIS_URL` متاحًا؛ يبقى LocMem للتطوير المحلي. Render blueprint يمرر مضيف Key Value إلى إعداد Redis.
- **التحقق:** `core.test_auth_throttling` يثبت أن الطلب السادس خلال النافذة يُرفض بـ429. يجب بعد النشر التحقق من إعداد Redis الفعلي في Render دون كشف بياناته، ثم اختبار الحد على بيئة اختبار من أكثر من عملية/عامل. **غير مفعل إنتاجيًا بعد لعدم وجود نشر.**

### P0 — استعادة كلمة المرور/الحساب

- **السبب الفعلي:** لم يكن هناك مسار استعادة أو قناة تثبت وصول المستخدم إلى الحساب.
- **الإصلاح المحلي:** أضيف طلب وإتمام استعادة عبر رابط بريد محدود المدة ولمرة واحدة، واستجابة عامة لا تكشف وجود الحساب، وتحديد معدل الطلبات، وإبطال رموز JWT عند تغيير كلمة المرور. الرابط يستخدم fragment حتى لا يصل رمز الاستعادة إلى خادم الويب في الطلب الأول. في الإنتاج، غياب إعداد البريد أو استخدام console backend يرجع 503؛ وفشل إرسال عابر يسجل تحذيرًا دون كشف وجود الحساب.
- **الملفات:** `backend/config/urls.py`، `backend/config/settings.py`، `backend/core/auth_views.py`، `backend/core/throttles.py`، `backend/core/templates/core/password_reset_email.txt`، `backend/core/templates/core/password_reset_subject.txt`، `backend/core/test_password_reset.py`، `frontend/src/App.jsx`، `frontend/src/i18n.js`.
- **التحقق المحلي:** 7 اختبارات استعادة تغطي عدم كشف وجود المستخدم حتى عند فشل SMTP، الإرسال، صلاحية لمرة واحدة، الرابط غير الصالح، إعداد البريد، وإبطال access/refresh tokens. الاختبارات المستهدفة نجحت.
- **ما بقي:** يلزم إعداد SMTP في Render: `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS`, `DEFAULT_FROM_EMAIL`, و`PASSWORD_RESET_FRONTEND_URL`. لا تُرسل قيم الأسرار في المحادثة أو Git. الحقل `User.email` اختياري؛ الحسابات بلا بريد صحيح لا تستعيد نفسها بهذا المسار وتحتاج إجراء دعم آمن. وصول المستخدم إلى صندوق البريد هو إثبات الملكية المستخدم؛ لا يوجد تحقق بريد منفصل.
- **أثر الإطلاق:** إعداد `CHECK_REVOKE_TOKEN=True` يجعل رموز JWT الصادرة قبل نشر هذا الإصدار غير صالحة؛ على المستخدمين تسجيل الدخول مجددًا مرة واحدة بعد النشر. لم يحدث نشر هنا. **يبقى مانعًا حتى إعداد البريد والتحقق منه في بيئة اختبار.**

### P0 — النسخ الاحتياطي والاستعادة

- **السبب الفعلي:** `render.yaml` يحدد PostgreSQL على خطة `free`. توثيق Render يؤكد أن Free لا يوفر PITR ولا نسخًا من لوحة التحكم. لا توجد نسخة اختبارية أو سجل استعادة.
- **الإجراء المحلي:** أضيفت خطوات تشغيل آمنة أدناه؛ لم يتم إنشاء/تنزيل نسخة من الإنتاج أو تعديل أي قاعدة. `pg_dump`, `pg_restore`, `psql` وDocker غير مثبتة محليًا، لذلك لم يمكن اختبار الاستعادة في هذا الجهاز.
- **ملفات الكود:** `render.yaml`، `backend/config/settings.py`. لا يلزم Migration لمعالجة هذا البند.
- **Runbook النسخ:** من جهاز موثوق ومشفّر خارج المستودع، نزّل أدوات PostgreSQL المتوافقة مع الإصدار، وخذ بيانات الاتصال من Render Dashboard دون لصقها في ملف بالمستودع. في PowerShell أدخل بيانات المضيف والمنفذ واسم قاعدة البيانات والمستخدم تفاعليًا، وأدخل كلمة المرور عبر مطالبة مخفية ثم عيّنها في متغير البيئة `PGPASSWORD` للجلسة فقط:
  `$env:PGHOST = Read-Host "Render external database host"; $env:PGPORT = Read-Host "Database port"; $env:PGDATABASE = Read-Host "Database name"; $env:PGUSER = Read-Host "Database user"; $env:PGSSLMODE = "require"; $credential = Get-Credential -UserName $env:PGUSER; $env:PGPASSWORD = $credential.GetNetworkCredential().Password`
  بعد ذلك شغّل:
  `pg_dump --host $env:PGHOST --port $env:PGPORT --username $env:PGUSER --dbname $env:PGDATABASE --format=custom --no-owner --no-acl --file $env:WASELNI_BACKUP_FILE`
  ثم تحقّق من قابلية القراءة باستخدام:
  `pg_restore --list $env:WASELNI_BACKUP_FILE`
  خزّن النسخة مشفّرة خارج المستودع، وطبّق سياسة احتفاظ/نسخ خارجية يحددها مالك الخدمة؛ لا تضع النسخة أو بيانات الاتصال في Git أو مجلد المشروع.
- **Runbook الاستعادة المعزولة:** جهّز PostgreSQL محليًا أو قاعدة اختبار منفصلة وفارغة، لا قاعدة Waselni الحالية. أنشئ قاعدة اختبار جديدة باسم مختلف، ثم نفّذ:
  `pg_restore --exit-on-error --no-owner --no-acl --dbname $env:WASELNI_TEST_DATABASE $env:WASELNI_BACKUP_FILE`
  لا تستخدم `--clean` أو `--create` ولا تستعد فوق قاعدة تحتوي بيانات. افحص اكتمال الجداول، شغّل `python manage.py check` ثم اختبارات قراءة تطبيقية على قاعدة الاختبار، وسجل التاريخ والنتيجة دون بيانات شخصية.
- **التحقق الحالي:** لم تُنفذ الأوامر؛ الأدوات غير موجودة ولا توجد نسخة اختبارية. يلزم أن يوفر مالك الخدمة بيئة PostgreSQL معزولة وأدوات محلية، ثم يختبر الاستعادة من نسخة غير إنتاجية. **ما زال مانعًا.**
- **مصادر Render:** [Recovery and Backups](https://render.com/docs/postgresql-backups) يذكر صراحةً عدم توفر PITR أو backups المُدارة للخطة المجانية، ويوثق `pg_dump`; [Cron Jobs](https://render.com/docs/cronjobs).

### P0 — منع الطلبات خارج مناطق الخدمة

- **السبب الفعلي:** لا يوجد نموذج أو إعداد مناطق خدمة ولا تحقق جغرافي في إنشاء الطلب. رغم تخزين إحداثيات المتجر ونقطة التسليم في `Order` (وإحداثيات الرحلة)، لا يوجد حد خدمة معتمد يمكن مقارنته.
- **الملفات:** `backend/core/models.py` (`Order` لا يتضمن مناطق خدمة)، `backend/core/serializers.py` (`OrderSerializer.validate` يتحقق من وجود إحداثيات التسليم لكنه لا يفحص التغطية)، ومسار إنشاء رحلة في `backend/core/views.py`.
- **ما يلزم من مالك العمل:** حدود معتمدة بصيغة قابلة للتطبيق (مضلعات/مناطق أو مسافة/نقطة مركزية)، تحديد هل تنطبق القاعدة على طلبات المتاجر والرحلات معًا، ومعالجة المناطق الحدودية. لم تُنشأ مناطق أو رسوم أو قيم افتراضية ولم تُضف Migration تخمينية.
- **التحقق المطلوب:** اختبارات داخل/خارج/على الحد لكل نوع طلب؛ إثبات أن الرفض يحدث قبل إنشاء الطلب أو حجز المخزون. **ما زال مانعًا ويتطلب قرارًا/بيانات خارجية.**

### P0 — جدولة الإكمال التلقائي بعد 12 ساعة

- **السبب الفعلي:** منطق الإكمال واستثناء الشكاوى موجود في `backend/core/services/order_completion.py`، ويوجد أمر `backend/core/management/commands/process_expired_order_confirmations.py`، لكن `render.yaml` لا يعرّف مشغّلًا دوريًا لهذا الأمر؛ لذا لا يوجد ضمان تشغيل عندما لا يفتح أحد التطبيق.
- **الملفات:** `backend/core/services/order_completion.py`، `backend/core/management/commands/process_expired_order_confirmations.py`، `render.yaml`.
- **القرار:** لم يتغير `render.yaml`: لا يحتوي على مشغّل. توثيق Render يذكر أن كل Cron Job لها حد أدنى **$1 شهريًا**؛ لذا لا يمكن إضافتها ضمن شرط عدم استخدام خدمة مدفوعة. تشغيل المهمة داخل web worker أو عند زيارة المستخدم ليس موثوقًا على خطة الويب المجانية.
- **المتاح:** الأمر `python manage.py process_expired_order_confirmations` موجود، ومنطق التأخير واستثناء الشكاوى في `backend/core/services/order_completion.py`. يمكن تشغيله دوريًا بعد توفير مشغّل موثوق.
- **ما يلزم خارجيًا:** موافقة مالك الخدمة على خدمة Render Cron (مع حدها الأدنى الحالي) أو اختيار مجدول خارجي مجاني موثوق وتزويده بطريقة آمنة للوصول إلى قاعدة البيانات. GitHub Actions المجدول ليس ضمانًا فوريًا ولا يملك حاليًا إعداد اتصال آمن بقاعدة الإنتاج؛ لم يُعتمد كبديل.
- **التحقق المطلوب:** اختبار بيئة منفصلة لطلب تجاوز 12 ساعة وطلب عليه شكوى مفتوحة، ثم إثبات سجل تنفيذ دوري. **ما زال مانعًا.**

### P1 — سجل أسباب تفعيل/إيقاف الحساب واعتماد الكابتن

- **السبب السابق:** `AdminUserDetailView` و`AdminCaptainApprovalView` كانا يغيران الحالات دون تسجيل السبب؛ `FinanceAccessAudit` يغطي صلاحية الموظف المالي فقط.
- **الملفات:** `backend/core/models.py`، `backend/core/views.py`، `backend/core/urls.py`، `backend/core/migrations/0016_adminaccountaudit.py`، `backend/core/test_admin_account_audit.py`، `backend/core/test_eligibility.py`، `frontend/src/App.jsx`، `frontend/src/i18n.js`.
- **الإصلاح المحلي:** Migration إضافية تنشئ `AdminAccountAudit` دون تعديل أو حذف بيانات قديمة. واجهة API تفرض سببًا عند تغيير الحالة، وتسجل المنفذ والقيمة السابقة والجديدة والتاريخ. سجل القراءة محمي بصلاحية المدير ولا توجد واجهة API لتعديل/حذف القيود. لوحة الإدارة تطلب السبب وتعرض أحدث السجلات باللغات الثلاث.
- **التحقق:** اختبارات تثبت رفض التغيير دون سبب، حفظ السبب والقيم، منع المستخدم غير الإداري من القراءة والتغيير، ونجاح مسار اعتماد الكابتن. **تم محليًا؛ يبقى تطبيق Migration ونشر الإصدار غير منفذين.** يجب عدم تطبيق Migration على الإنتاج قبل مراجعة حالة Git والموافقة على النشر.

### P1 — استمرارية الصور والوثائق المرفوعة

- **السبب الفعلي المثبت:** `WaselniMediaStorage` في `backend/core/storage.py` يرجع إلى التخزين المحلي عند غياب إعداد ImageKit، وقد تظهر الملفات المحلية على Render مؤقتًا وتفقد عند إعادة التشغيل. `render.yaml` يعرّف `IMAGEKIT_PRIVATE_KEY` كمتغير يُضبط يدويًا (`sync: false`)؛ لا يمكن معرفة إن كان مضبوطًا على الخدمة الحية من المستودع.
- **الملفات:** `backend/core/storage.py`، `backend/core/checks.py`، `backend/config/settings.py`، `render.yaml`.
- **توضيح مهم:** أضيفت فحوص إعداد Redis والبريد في `backend/core/checks.py`؛ تعرض تحذيرًا بلا قيم متغيرات. `render.yaml` يعرّف `REDIS_HOST/PORT` عبر Key Value مجاني، و`IMAGEKIT_PRIVATE_KEY` و`IMAGEKIT_PUBLIC_KEY` كقيم يدوية. هذا يثبت الإعداد المقصود فقط، ولا يثبت الحالة الفعلية لخدمة Render.
- **الإجراء المطلوب:** في لوحة Render، تحقق من وجود متغيرات ImageKit المطلوبة دون نسخ القيم، ثم ارفع ملف اختبار غير شخصي في بيئة اختبار وتحقق من ظهوره بعد إعادة تشغيل. تحقق كذلك من أن `REDIS_HOST/PORT` يشيران إلى `waselni-kv` وأن اتصال Redis ناجح. لا تغيّر الأسرار عشوائيًا.
- **التحقق بعد التنفيذ:** رفع ملف اختبار غير شخصي، التحقق من ظهوره بعد إعادة تشغيل بيئة اختبار، والتحقق من بقاء وثائق الكابتن خاصة. **ما زال مانعًا حتى التحقق الحي.**

## تصنيف الاعتماد بعد هذه المتابعة

### جاهز محليًا

- تدفق استعادة كلمة المرور بالكود، مع رسالة عامة ومعدل طلبات ورمز محدود المدة لمرة واحدة.
- إبطال JWT عند تغيير كلمة المرور، وفحوص آلية تحذر من غياب Redis أو بريد الإنتاج.
- خطوات آمنة موثقة لأخذ نسخة من PostgreSQL واستعادتها إلى قاعدة جديدة معزولة؛ **لم تُنفذ الاستعادة**.

### تحسين غير عاجل

- تحذير Vite من أن حزمة كل بوابة أكبر من 500KB؛ البناء ناجح ولا يمنع تصحيح الوظائف الحالية.

### يمنع الاعتماد حتى الإصلاح/التحقق

- إعداد SMTP الفعلي واختبار رسالة استعادة في بيئة غير إنتاجية، ومعالجة الحسابات التي لا تملك بريدًا.
- نسخة احتياطية فعلية وسياسة احتفاظ واختبار استعادة منفصل. Render Free لا يقدم backup أو PITR مُدارًا.
- تزويد حدود مناطق خدمة معتمدة ثم تطبيقها واختبارها على مسارات الطلب.
- توفير وتشغيل مجدول تلقائي موثوق بعد 12 ساعة؛ خيار Render Cron الحالي مدفوع.
- التحقق من إعداد ImageKit وRedis في Render، واختبار رفع/إعادة تشغيل واتصال مشترك فعلي.

## الترتيب التنفيذي

1. **P0:** حماية تسجيل الدخول — إصلاح الكود موجود، والتحقق الإنتاجي من Redis والنشر ما زال مطلوبًا.
2. **P0:** الاستعادة الآمنة للحساب، والنسخ الاحتياطي/الاستعادة، ومناطق التغطية، ومشغّل الإكمال — كل منها يحتاج إعدادًا أو سياسة/قرارًا خارجيًا؛ تجنب التنفيذ التخميني.
3. **P1:** تدقيق تغييرات الحساب والكابتن — إصلاح الكود وMigration واختبارات محلية تمت؛ يلزم لاحقًا اعتماد ونشر.
4. **P1:** استمرارية الوسائط — إعداد ImageKit في Render غير قابل للتحقق من ملفات المشروع وحدها.

## نتائج التحقق المحلي

- اختبار تحديد محاولات الدخول: **نجح** (`core.test_auth_throttling`: 1 اختبار).
- اختبارات الاستعادة وفحوص إعداد البريد/Redis/ImageKit: **نجحت** (17 اختبارًا عبر `core.test_password_reset`, `core.test_storage_checks`, و`core.test_auth_throttling`؛ شملت إبطال access/refresh token بعد إعادة تعيين كلمة المرور).
- اختبارات سجل التدقيق: **نجحت** (3 اختبارات).
- اختبارات اعتماد الكابتن والأهلية: **نجحت** (49 اختبارًا).
- Migration: `0016_adminaccountaudit.py` Migration إضافية؛ فحص `makemigrations --check --dry-run`: **لا تغييرات معلقة**.
- `manage.py makemigrations --check --dry-run`: **لا تغييرات معلقة**؛ و`manage.py check`: **نجح** في الإعداد المحلي. أثناء الاختبارات ظهرت تحذيرات ImageKit وSMTP وRedis في إعداد الاختبار، ولا تثبت حالة Render.
- بناء Customer وCaptain وMerchant وAdmin بعد تعديل الواجهة: **نجح**. ظهر تحذير Vite المعتاد عن حجم الحزمة الأكبر من 500KB.
- TypeScript (`npm run typecheck`): **نجح**.
- Build (`npm run build:all-portals`): **نجح للبوابات الأربع**؛ بقي تحذير حجم chunk أكبر من 500KB.
- الاختبارات الكاملة لـBackend: **نجحت** — 256 اختبارًا، `OK`، زمن 814.364 ثانية، وشملت اختبار فشل SMTP الأخير.
- ظهرت تحذيرات الاختبار المتوقعة لبيئة التطوير: ImageKit غير مضبوط محليًا، ومفتاح JWT المحلي الافتراضي أقصر من توصية HS256. لا تثبت هذه التحذيرات حالة إعدادات Render؛ يجب التحقق من القيم الإنتاجية دون كشفها.
- لا توجد اختبارات فعلية على مستخدمين أو طلبات إنتاج. لم يُشغّل Deploy أو Migration على الإنتاج.

## Git والتغييرات

- عند إجراء الفحوص: فرع العمل `mahmoudqutama1997-waselni-order-lifecycle` وHEAD `f846528`; هذا الـHEAD يطابق `origin/release/phase1-captain-docs-2026-11-12`.
- فحوص الجاهزية لا تعني نشرًا؛ لم يحدث Deploy أو تطبيق Migration على قاعدة إنتاج. تفاصيل نقل التغييرات ورقم Commit النقل مذكورة في تسليم المهمة.
- لم يُحذف أو يُستبدل أي عمل محلي، ولم تُطبق Migration على قاعدة إنتاج.
- التقرير السابق `WASELNI_PRODUCTION_READINESS_REPORT.md` محفوظ كما هو.
- تقرير المتابعة هذا ملف جديد: `WASELNI_PRODUCTION_READINESS_REPORT_FINAL.md`.
- الملفات المعدلة الظاهرة في `git status`: `README.md`, `backend/config/settings.py`, `backend/config/urls.py`, `backend/core/checks.py`, `backend/core/models.py`, `backend/core/test_eligibility.py`, `backend/core/test_storage_checks.py`, `backend/core/urls.py`, `backend/core/views.py`, `frontend/src/App.jsx`, `frontend/src/i18n.js`.
- الملفات الجديدة/غير المتتبعة الظاهرة في `git status`: `WASELNI_PRODUCTION_READINESS_REPORT.md`, `WASELNI_PRODUCTION_READINESS_REPORT_FINAL.md`, `backend/core/auth_views.py`, `backend/core/migrations/0016_adminaccountaudit.py`, `backend/core/templates/core/password_reset_email.txt`, `backend/core/templates/core/password_reset_subject.txt`, `backend/core/test_admin_account_audit.py`, `backend/core/test_auth_throttling.py`, `backend/core/test_password_reset.py`, `backend/core/throttles.py`.
- لم يُنتقل إلى `main`، ولم يحدث Force push.

## قرار الاعتماد

لا يُعتمد الإصدار حاليًا. استعادة الحساب مطبقة محليًا واختباراتها ناجحة، لكن تفعيل البريد على Render والتحقق منه لازمان. النسخ الاحتياطي والاستعادة المعزولة غير مختبرين، ومناطق الخدمة تتطلب سياسة معتمدة، والمجدول يحتاج موردًا خارجيًا، وإعداد ImageKit/Redis الحي غير متحقق. نجحت Backend suite كاملة وTypeScript وبناء البوابات الأربع محليًا؛ هذه النتائج لا تثبت التكامل أو الإعداد الحي. لم يحدث Deploy أو Migration إنتاجية.
