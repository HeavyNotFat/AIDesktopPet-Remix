<?php

declare(strict_types=1);

namespace UGCTest;

/**
 * 极简 HTTP 客户端：只依赖 php 自带的流包装器（本机没有 curl 扩展）。
 */
final class Http
{
    /** @var array<string, string> */
    private array $cookies = [];
    private string $csrf = '';

    public function __construct(private string $baseUrl)
    {
    }

    /** 让后续写请求自动带上 CSRF 头（和前端行为一致）。 */
    public function setCsrf(string $token): void
    {
        $this->csrf = $token;
    }

    public function withBase(string $baseUrl): self
    {
        $clone = clone $this;
        $clone->baseUrl = rtrim($baseUrl, '/');
        return $clone;
    }

    /**
     * @param array<string, mixed>|null $json
     * @param array<string, string> $headers
     * @return array{status: int, headers: array<string, string>, body: string, json: array<string, mixed>|null}
     */
    public function request(string $method, string $path, ?array $json = null, array $headers = [], ?string $rawBody = null): array
    {
        $url = str_starts_with($path, 'http') ? $path : $this->baseUrl . $path;
        $headerLines = ['Accept: application/json', 'Connection: close'];
        if ($this->csrf !== '' && !in_array(strtoupper($method), ['GET', 'HEAD', 'OPTIONS'], true)) {
            $headers += ['X-CSRF-Token' => $this->csrf];
        }
        foreach ($headers as $name => $value) {
            $headerLines[] = $name . ': ' . $value;
        }

        $body = $rawBody;
        if ($json !== null) {
            $body = json_encode($json, JSON_UNESCAPED_UNICODE);
            $headerLines[] = 'Content-Type: application/json';
        }
        if ($body !== null) {
            $headerLines[] = 'Content-Length: ' . strlen($body);
        }
        if ($this->cookies !== []) {
            $pairs = [];
            foreach ($this->cookies as $name => $value) {
                $pairs[] = $name . '=' . $value;
            }
            $headerLines[] = 'Cookie: ' . implode('; ', $pairs);
        }

        $context = stream_context_create([
            'http' => [
                'method' => $method,
                'header' => implode("\r\n", $headerLines),
                'content' => $body ?? '',
                'ignore_errors' => true,
                'follow_location' => 0,
                'timeout' => 60,
            ],
        ]);

        $responseBody = @file_get_contents($url, false, $context);
        $responseHeaders = $http_response_header ?? [];
        $status = 0;
        $parsed = [];
        foreach ($responseHeaders as $line) {
            if (preg_match('#^HTTP/\S+\s+(\d{3})#', $line, $matches)) {
                $status = (int) $matches[1];
                $parsed = [];
                continue;
            }
            $parts = explode(':', $line, 2);
            if (count($parts) === 2) {
                $parsed[strtolower(trim($parts[0]))] = trim($parts[1]);
            }
        }

        $this->storeCookies($responseHeaders);

        $decoded = null;
        if (is_string($responseBody) && $responseBody !== '') {
            $maybe = json_decode($responseBody, true);
            $decoded = is_array($maybe) ? $maybe : null;
        }

        return [
            'status' => $status,
            'headers' => $parsed,
            'body' => is_string($responseBody) ? $responseBody : '',
            'json' => $decoded,
        ];
    }

    /** @param array<int, string> $headerLines */
    private function storeCookies(array $headerLines): void
    {
        foreach ($headerLines as $line) {
            if (!preg_match('/^Set-Cookie:\s*([^=]+)=([^;]*)/i', $line, $matches)) {
                continue;
            }
            $name = trim($matches[1]);
            $value = trim($matches[2]);
            if ($value === '') {
                unset($this->cookies[$name]);
                continue;
            }
            $this->cookies[$name] = $value;
        }
    }

    public function cookie(string $name): string
    {
        return $this->cookies[$name] ?? '';
    }

    /** @param array<string, string|array{name: string, content: string, type?: string}> $fields @param array<string, string> $headers */
    public function multipart(string $path, array $fields, array $headers = []): array
    {
        $boundary = '----ugctest' . bin2hex(random_bytes(8));
        $body = '';
        foreach ($fields as $name => $value) {
            $body .= '--' . $boundary . "\r\n";
            if (is_array($value)) {
                $body .= sprintf(
                    "Content-Disposition: form-data; name=\"%s\"; filename=\"%s\"\r\n",
                    $name,
                    $value['name']
                );
                $body .= 'Content-Type: ' . ($value['type'] ?? 'application/octet-stream') . "\r\n\r\n";
                $body .= $value['content'] . "\r\n";
                continue;
            }
            $body .= sprintf("Content-Disposition: form-data; name=\"%s\"\r\n\r\n", $name);
            $body .= $value . "\r\n";
        }
        $body .= '--' . $boundary . "--\r\n";

        return $this->request(
            'POST',
            $path,
            null,
            $headers + ['Content-Type' => 'multipart/form-data; boundary=' . $boundary],
            $body
        );
    }
}
