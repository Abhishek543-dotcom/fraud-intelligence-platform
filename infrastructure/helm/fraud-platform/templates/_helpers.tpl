{{/*
Expand the name of the chart.
*/}}
{{- define "fraud-platform.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "fraud-platform.fullname" -}}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "fraud-platform.labels" -}}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: fraud-intelligence-platform
{{- end }}

{{/*
Selector labels
*/}}
{{- define "fraud-platform.selectorLabels" -}}
app.kubernetes.io/name: {{ include "fraud-platform.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Namespace
*/}}
{{- define "fraud-platform.namespace" -}}
{{- .Values.global.namespace | default "fraud-platform" }}
{{- end }}
