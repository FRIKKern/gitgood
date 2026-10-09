import {provisionConfiguration} from '../apps/forge/priv/operations/recovery-configuration.mjs'
try{
  const required=name=>{const value=process.env[name];if(!value)throw new Error('missing configuration');return value}
  await provisionConfiguration({directory:required('GITGOOD_RECOVERY_CONFIGURATION'),forge:process.env,
    web:{NODE_ENV:'production',PORT:required('GITGOOD_WEB_PORT'),GITGOOD_API_URL:required('GITGOOD_API_URL'),
      GITGOOD_PROXY_KEY:required('GITGOOD_PROXY_KEY')},
    certificate:required('GITGOOD_TLS_CERTIFICATE'),tlsKey:required('GITGOOD_TLS_KEY'),sourceCa:process.env.GITGOOD_BARKPARK_CA})
  process.stdout.write('Private recovery configuration provisioned\n')
}catch{process.stderr.write('Recovery configuration provisioning refused\n');process.exitCode=1}
