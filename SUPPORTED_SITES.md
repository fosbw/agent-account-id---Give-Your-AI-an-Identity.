# Agent Account Google ID — المواقع ومكان التشغيل والمتطلبات

## بص، الأداة دي بتشتغل فين؟

الأداة دي مش موقع ولا تطبيق لوحده. هي Tool/Skill بتتحط جنب الـ Agent اللي أنت بتستخدمه. أنت بتجيب Claude Code أو Codex أو أي Agent عنده طريقة يستدعي Tools، وبعدها تقول له المهمة والمدة. الأداة تمسك الجلسة والمتصفح والوقت والمراقبة والإيقاف.

اسم المنتج الظاهر للمستخدم هو:

> **Agent Account Google ID — Give Your AI an Identity**

اسم الأمر القديم `agentguard` موجود فقط عشان التوافق مع النسخة الأولى. وسيتم توفير alias باسم المنتج للناس التي تريد استدعاء الأداة باسمها الكامل.

## المواقع ومسارات الدخول

المهم تفهم النقطة دي: مش كل موقع عنده زر Google يبقى الأداة تقدر تدخله تلقائيًا بنفس الطريقة. الموقع لازم يكون عنده مسار رسمي يقبل Google OAuth أو OIDC أو SSO أو API. القائمة التالية بتوضح أقرب أماكن للاستخدام، والفرق بين الدعم المباشر والدعم المشروط.

| الموقع أو الخدمة | المسار الممكن | الحالة في المشروع |
|---|---|---|
| Google Workspace وGoogle Cloud | Google OAuth أو Service Account أو Workspace SSO | هوية Google metadata وOAuth identity flow موجودان؛ صلاحيات Gmail وDrive والإدارة غير مفعلة. |
| Microsoft Entra External ID أو تطبيق مؤسسة يستخدم Microsoft SSO | Google Federation/OIDC إذا كانت المؤسسة مفعّلتها | ممكن فقط بعد إعداد Federation من مالك المؤسسة؛ ليس دخولًا عامًا لكل حسابات Microsoft. |
| Notion | OAuth integration أو API رسمي | مناسب كـ Adapter API بعد تسجيل Integration وتحديد الصلاحيات؛ زر Google وحده لا يكفي. |
| Slack | OAuth app أو SSO للمؤسسة | مناسب بعد إنشاء App أو إعداد SSO من مالك Workspace؛ لا يوجد دخول عام بحساب Google لكل Workspace. |
| GitLab | OAuth أو Group SSO أو API | مناسب عندما يفعّل المالك Google/OIDC أو يستخدم OAuth/API رسمي. |
| Atlassian Cloud | Google login أو SAML/SSO أو API OAuth | مشروط بإعداد المؤسسة ونوع الحساب والصلاحيات. |
| Linear | OAuth integration أو API | مناسب لتشغيل Agent بصلاحيات محددة؛ لا يعتمد على تخمين كلمة مرور أو Cookie. |
| GitHub | GitHub App أو OAuth أو Enterprise SSO | مناسب بتكامل GitHub رسمي؛ GitHub ليس موقعًا نعلن أنه يقبل حساب Google مباشرة في كل الحالات. |
| أي SaaS آخر | OAuth/OIDC/API موثق من المزود | يضاف له Adapter مستقل بعد مراجعة طريقة الدخول والصلاحيات. |

## المواقع التي لا نقول إنها مدعومة تلقائيًا

الموقع الذي لا يقدم OAuth أو OIDC أو SSO أو API رسمي لا نعتبره مدعومًا لمجرد أنه يفتح في Chrome. كذلك لا نعتبر الحسابات التي تحتاج CAPTCHA أو MFA غير قابل للبرمجة دليلًا على أن الأداة تستطيع تجاوزها. الأداة لا تستخرج Password أو Cookie ولا تنقل Session من شخص إلى شخص.

لو قلت للـ Agent: «ادخل Microsoft»، لازم يكون المقصود خدمة Microsoft محددة ومهيأة بطريقة تسمح بهوية Google أو بهوية Microsoft/Entra مصرح بها. Microsoft 365 العادي لا يتحول تلقائيًا إلى Google login لمجرد أن عندك حساب Google.

## الـ Agents التي تشتغل معها الأداة

| Agent أو بيئة | الوضع | طريقة الاستخدام |
|---|---|---|
| Claude Code | تكامل منفذ | Claude Hook يستدعي الأداة ويسجل الأحداث ويخضع الجلسة للسياسة. |
| Codex CLI | تكامل منفذ | Wrapper يشغل Codex داخل Supervisor مع TTL والهوية والمتصفح. |
| Gemini CLI | تشغيل عام ممكن، Adapter متخصص لاحق | يمكن تشغيل أي أمر محلي عبر Supervisor؛ تعليمات Gemini المتخصصة ليست Adapter مكتملًا داخل المشروع. |
| GitHub Copilot CLI | تشغيل عام ممكن، Adapter متخصص لاحق | يحتاج إعداد Hooks أو MCP من جهة Copilot؛ ليس تكاملًا مكتملًا حاليًا. |
| MCP-compatible Agent | واجهة مناسبة | يمكن إضافة MCP server عندما نحدد عقد التشغيل والصلاحيات للمزود. |
| أي Agent يشغل command محلي | ممكن على مستوى Supervisor | يشغل الأمر تحت TTL، لكن ربط الهوية والمتصفح يحتاج دعمًا صريحًا من البيئة. |

## أماكن تشغيل الأداة

الأداة حاليًا **local-first**. يعني الكود يشتغل على البيئة التي أنت مثبت فيها المشروع والـ Agent.

| المكان | الدعم الحالي |
|---|---|
| Linux | مناسب للتشغيل الكامل؛ يدعم process groups وpause/resume وChromium إذا كان مثبتًا. |
| macOS | مناسب غالبًا لمسار الجلسة والمتصفح؛ بعض تفاصيل process control تعتمد على البيئة. |
| WSL | مناسب لتشغيل Python والـ Agent؛ يجب أن يكون Chromium والـ Agent في نفس البيئة أو أن تحدد مسارهما. |
| Windows native | تشغيل Supervisor ممكن، لكن Pause/Resume وإدارة process groups ليست بنفس ضمانات POSIX الحالية. |
| Docker أو VM | مناسب للعزل الأقوى إذا جهز المستخدم Chromium والـ Agent والشبكة. |
| CI/CD | مناسب لاختبارات CLI غير التفاعلية؛ لا نعتبره مكانًا مناسبًا لهوية متصفح حقيقية بدون إعداد Secret Manager وBrowser Runtime مصرح. |
| Cloud browser أو بث عن بُعد | ليس مستضافًا في المشروع الحالي؛ يحتاج بيئة نشر مستقلة ومصادقة للبث. |
| هاتف المستخدم | لا يوجد ربط مباشر حاليًا بين الهاتف والـ Sandbox؛ يحتاج Browser Runtime أو خدمة Remote Desktop مخصصة. |

## متطلبات التشغيل

بص، عشان تشغل النسخة الحالية تحتاج Python 3.10 أو أحدث، وGit، والـ Agent الذي تريد تشغيله مثل Claude Code أو Codex، ومساحة عمل واضحة، وChromium أو متصفح Chromium-compatible إذا كنت ستستخدم مسار المتصفح، وقائمة domains مسموحة.

لو ستستخدم Google OAuth الرسمي، تحتاج Installed-App OAuth Client من Google Cloud، وهوية يملكها المستخدم أو المؤسسة، ونطاقات الهوية الأساسية فقط. الأمر الحالي لا ينشئ حساب Google، ولا يطلب Gmail أو Drive أو Admin scopes، ولا يحفظ Access Token أو Refresh Token.

لو ستستخدم موقعًا خارجيًا، تحتاج أن يكون الموقع داعمًا لمسار OAuth/OIDC/SSO/API رسمي، وأن يكون التكامل مضافًا إلى allowlist، وأن تكون الصلاحيات معروفة وقابلة للإلغاء. لا تضع Password أو Cookie أو Token في GitHub أو في الشات أو في command line.

## طريقة الاستخدام التي تقصدها

```text
المستخدم: ادخل على الخدمة المحددة، استخدم Agent Account Google ID، ومعاك ساعة.

الـ Agent: يستدعي الأداة ويطلب جلسة لمدة ساعة.

الأداة: تنشئ Session وBrowser Profile منفصل، تربط الهوية المصرح بها، تشغل Timer، وتعرض Live Events.

الـ Agent: ينفذ المهمة من خلال Adapter رسمي أو Browser Runtime مصرح به.

المستخدم: يشاهد الجلسة ويقدر يعمل Pause أو Stop أو Kill.

الأداة: عند انتهاء الساعة توقف كل شيء وتمسح البيانات المؤقتة.
```

المستخدم لا يريد يكتب عشرين أمرًا. هذا هو سبب وجود الـ Skill: المستخدم يقول المهمة والمدة، والـ Agent يستدعي الأداة. لكن كل موقع له طريقة دخول وصلاحيات منفصلة، ولا يوجد مفتاح سحري يجعل Google login يعمل في كل خدمة.

## ما هو منفذ الآن وما هو جاهز للإضافة

المنفذ الآن هو Supervisor للجلسة، Timer، process control، الهوية المرجعية، Google OAuth الرسمي للهوية فقط، المتصفح المعزول، domain allowlist، Live Events، Browser Watch، Cleanup، وClaude/Codex adapters.

الجاهز للإضافة هو Adapter مستقل لكل خدمة تسمح رسميًا بـ OAuth/OIDC/API، مع تعريف الصلاحيات والإلغاء والـ retention. أما إنشاء حسابات Google تلقائيًا أو توزيعها أو استخدام كلمة مرور أو Cookie للدخول في مواقع متعددة فليس جزءًا من الكود.

## مراجع المزودين

[1]: https://developers.google.com/identity/protocols/oauth2 "Google OAuth 2.0"
[2]: https://developers.google.com/identity/openid-connect/openid-connect "Google OpenID Connect"
[3]: https://learn.microsoft.com/en-us/entra/external-id/customers/how-to-google-federation-customers "Microsoft Entra External ID Google federation"
[4]: https://developers.notion.com/docs/authorization "Notion authorization"
[5]: https://api.slack.com/authentication/oauth-v2 "Slack OAuth v2"
[6]: https://docs.gitlab.com/api/oauth/ "GitLab OAuth"
[7]: https://developer.atlassian.com/cloud/jira/platform/oauth-2-3lo-apps/ "Atlassian OAuth 2.0"
[8]: https://linear.app/developers/oauth "Linear OAuth"
[9]: https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps "GitHub OAuth Apps"
