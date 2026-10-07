<?php

namespace OCA\NxtWorkspace\Controller;

use OCP\AppFramework\Controller;
use OCP\AppFramework\Http\Attribute\NoAdminRequired;
use OCP\AppFramework\Http\Attribute\NoCSRFRequired;
use OCP\AppFramework\Http\JSONResponse;
use OCP\Http\Client\IClientService;
use OCP\IGroupManager;
use OCP\IRequest;
use OCP\IUserSession;

class ApiController extends Controller
{
    public function __construct(
        string $appName,
        IRequest $request,
        private IUserSession $userSession,
        private IGroupManager $groupManager,
        private IClientService $clientService,
    ) {
        parent::__construct($appName, $request);
    }

    #[NoAdminRequired]
    #[NoCSRFRequired]
    public function me(): JSONResponse
    {
        $user = $this->userSession->getUser();

        if ($user === null) {
            return new JSONResponse(
                ['error' => 'Not authenticated'],
                401
            );
        }

        $userId = $user->getUID();

        return new JSONResponse([
            'user_id' => $userId,
            'display_name' => $user->getDisplayName(),
            'groups' => $this->groupManager->getUserGroupIds($user),
            'is_admin' => $this->groupManager->isAdmin($userId),
        ]);
    }

    #[NoAdminRequired]
    #[NoCSRFRequired]
    public function health(): JSONResponse
    {
        try {
            $client = $this->clientService->newClient();

            $response = $client->get(
                'http://rag-api:8058/health',
                [
                    'timeout' => 10,
                ]
            );

            $data = json_decode($response->getBody(), true);

            return new JSONResponse(
                is_array($data) ? $data : ['status' => 'unknown'],
                $response->getStatusCode()
            );
        } catch (\Throwable $e) {
            return new JSONResponse(
                [
                    'status' => 'unreachable',
                    'detail' => $e->getMessage(),
                ],
                502
            );
        }
    }

    #[NoAdminRequired]
    #[NoCSRFRequired]
    public function chat(): JSONResponse
    {
        $user = $this->userSession->getUser();

        if ($user === null) {
            return new JSONResponse(
                ['error' => 'Not authenticated'],
                401
            );
        }

        $body = json_decode(file_get_contents('php://input'), true);

        if (!is_array($body) || empty(trim((string)($body['message'] ?? '')))) {
            return new JSONResponse(
                ['error' => 'Message is required'],
                422
            );
        }

        $userId = $user->getUID();
        $groups = $this->groupManager->getUserGroupIds($user);

        $allowedGroups = $this->groupManager->isAdmin($userId)
            ? null
            : array_values($groups);

        $token = getenv('NXT_RAG_INTERNAL_TOKEN');

        if ($token === false || $token === '') {
            return new JSONResponse(
                ['error' => 'NXT AI backend token is not configured'],
                503
            );
        }

        try {
            $client = $this->clientService->newClient();

            $response = $client->post(
                'http://rag-api:8058/nxt/chat',
                [
                    'headers' => [
                        'Content-Type' => 'application/json',
                        'X-NXT-RAG-Token' => $token,
                    ],
                    'body' => json_encode([
                        'message' => (string)$body['message'],
                        'session_id' => $body['session_id'] ?? null,
                        'user_id' => $userId,
                        'allowed_groups' => $allowedGroups,
                    ]),
                    'timeout' => 120,
                ]
            );

            $data = json_decode($response->getBody(), true);

            return new JSONResponse(
                is_array($data) ? $data : ['error' => 'Invalid RAG response'],
                $response->getStatusCode()
            );
        } catch (\Throwable $e) {
            return new JSONResponse(
                [
                    'error' => 'Failed to contact RAG API',
                    'detail' => $e->getMessage(),
                ],
                502
            );
        }
    }
}